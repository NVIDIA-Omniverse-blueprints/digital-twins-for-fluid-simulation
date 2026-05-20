from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    CfnOutput,
    Duration,
    Fn,
    aws_ssm as ssm
)
from constructs import Construct
import os


class NimComputeStack(Stack):
    """
    NIM compute stack creating EC2 instance for NIM inference service.
    Runs NIM container separately from Omniverse/frontend.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        repo_bucket: s3.IBucket = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # NGC secret name - imported from ConfigStack export at deploy time.
        # Falls back to context variable for backwards compatibility (e.g. manual secret creation).
        ngc_secret_name = (
            self.node.try_get_context("ngcSecretName")
            or Fn.import_value("OmniverseCAEConfigStack-NGCSecretName")
        )

        ngc_api_key_secret = secretsmanager.Secret.from_secret_name_v2(
            self,
            "NGCAPIKeySecret",
            secret_name=ngc_secret_name,
        )

        # IAM Role for EC2 instance
        instance_role = iam.Role(
            self,
            "NimInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Role for NIM EC2 instance",
            managed_policies=[
                # SSM Session Manager - allows shell access without SSH/bastion
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # Secrets Manager - read NGC API key
        ngc_api_key_secret.grant_read(instance_role)

        # S3 - read repo artifact bucket
        if repo_bucket is None:
            raise ValueError("repo_bucket is required — source code is always pulled from S3")
        repo_bucket.grant_read(instance_role)

        # Security Group for NIM instance - NO INBOUND ACCESS initially
        security_group = ec2.SecurityGroup(
            self,
            "NimSecurityGroup",
            vpc=vpc,
            description="Security group for NIM instance - access controlled by Omniverse stack",
            allow_all_outbound=True,
        )

        # Store security group for export
        self.security_group = security_group

        # User data script to setup NIM instance
        user_data = ec2.UserData.for_linux()

        # Read the user data script from file
        user_data_script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "lib",
            "user_data",
            "nim.sh"
        )

        with open(user_data_script_path, "r") as f:
            user_data_script = f.read()

        # Replace placeholders with actual values
        user_data_script = user_data_script.replace("${NGC_SECRET_NAME}", ngc_api_key_secret.secret_name)
        user_data_script = user_data_script.replace("${AWS_REGION}", self.region)

        # S3 source substitutions
        from stacks.repo_artifact_stack import RepoArtifactStack
        user_data_script = user_data_script.replace("${REPO_S3_BUCKET}", repo_bucket.bucket_name)
        user_data_script = user_data_script.replace("${REPO_S3_PREFIX}", RepoArtifactStack.REPO_PREFIX)

        # Add the script to user data
        user_data.add_commands(user_data_script)

        # Use Deep Learning AMI with NVIDIA drivers pre-installed
        machine_image = ec2.MachineImage.lookup(
            name="Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.* (Ubuntu 22.04) *",
            owners=["amazon"],
        )

        # EC2 Instance - g5.xlarge with 1x A10G GPU (sufficient for NIM)
        # NIM typically needs 1 GPU, so we use smaller instance
        instance = ec2.Instance(
            self,
            "NimInstance",
            instance_type=ec2.InstanceType("g5.xlarge"),
            machine_image=machine_image,
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC,
                one_per_az=False,
            ),
            security_group=security_group,
            role=instance_role,
            user_data=user_data,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/sda1",
                    volume=ec2.BlockDeviceVolume.ebs(
                        volume_size=200,  # Smaller than main instance
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        iops=3000,
                        #throughput=125,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            user_data_causes_replacement=True,
            require_imdsv2=True,
        )

        # No Elastic IP needed - NIM is accessed via private IP within VPC
        # Store instance and security group for cross-stack references
        self.instance = instance
        self.security_group = security_group
        self.nim_private_ip = instance.instance_private_ip



        self.nim_ip_parameter = ssm.StringParameter(
            self,
            "NIMIPParameter",
            parameter_name="/omniverse-cae/nim-ip",
            string_value=instance.instance_private_ip,
        )


        # Outputs
        CfnOutput(
            self,
            "NimInstanceId",
            value=instance.instance_id,
            description="NIM EC2 Instance ID",
            export_name=f"{self.stack_name}-InstanceId",
        )

        CfnOutput(
            self,
            "NimInstancePrivateIP",
            value=instance.instance_private_ip,
            description="NIM private IP address for internal VPC communication",
            export_name=f"{self.stack_name}-PrivateIP",
        )

        CfnOutput(
            self,
            "NimInstancePublicIP",
            value=instance.instance_public_ip,
            description="NIM public IP address (for debugging - changes on restart)",
        )

        CfnOutput(
            self,
            "NimAPIURL",
            value=f"http://{instance.instance_private_ip}:8080",
            description="NIM API endpoint (internal VPC)",
            export_name=f"{self.stack_name}-APIURL",
        )

        CfnOutput(
            self,
            "NimSSMConnectCommand",
            value=f"aws ssm start-session --target {instance.instance_id}",
            description="Connect to NIM instance via Session Manager",
        )

        CfnOutput(
            self,
            "NimSecurityGroupId",
            value=security_group.security_group_id,
            description="NIM Security Group ID",
            export_name=f"{self.stack_name}-SecurityGroupId",
        )

        CfnOutput(
            self,
            "NGCSecretName",
            value=ngc_secret_name,
            description="Secrets Manager secret name containing NGC API key",
        )
