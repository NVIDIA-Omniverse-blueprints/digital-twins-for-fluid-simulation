from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_s3 as s3,
    aws_secretsmanager as secretsmanager,
    aws_ssm as ssm,
    CfnOutput,
    Duration,
    Fn,
)
from constructs import Construct
import os


class ComputeStack(Stack):
    """
    Compute stack creating EC2 instance for Omniverse CAE Blueprint.
    Runs Web frontend and Kit streaming. Can connect to separate NIM instance.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        use_external_nim: bool = False,
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
            "OmniverseInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="Role for Omniverse CAE EC2 instance",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchAgentServerPolicy"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "AmazonSSMManagedInstanceCore"
                ),
            ],
        )

        # Grant permission to read NGC API key
        ngc_api_key_secret.grant_read(instance_role)

        # Grant read access to the repo artifact bucket.
        if repo_bucket is not None:
            repo_bucket.grant_read(instance_role)

        # Security Group for Omniverse instance - RESTRICTIVE by default
        security_group = ec2.SecurityGroup(
            self,
            "OmniverseSecurityGroup",
            vpc=vpc,
            description="Security group for Omniverse CAE instance - restricted access",
            allow_all_outbound=True,
        )

        # If using external NIM, we'll need to add a rule post-deployment or use a custom resource
        # The NIM security group will need to allow traffic from this security group
        # This is handled via the configure-nim-access.sh script or manually

        # Store security group for export
        self.security_group = security_group

        # User data script to setup instance - loaded from external file
        user_data = ec2.UserData.for_linux()

        # Read the user data script from file
        user_data_script_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "lib",
            "user_data",
            "compute.sh"
        )

        with open(user_data_script_path, "r") as f:
            user_data_script = f.read()

        # Replace placeholders with actual values
        user_data_script = user_data_script.replace(
            "${NGC_SECRET_NAME}",
            ngc_api_key_secret.secret_name
        )
        user_data_script = user_data_script.replace(
            "${AWS_REGION}",
            self.region
        )

        # Add NIM endpoint configuration
        if use_external_nim:
            # Set placeholder - user data will read NIM IP from instance tags
            user_data_script = user_data_script.replace(
                "${NIM_TRITON_IP_ADDRESS}",
                "RETRIEVE_FROM_SSM"  # User data will replace this
            )
            user_data_script = user_data_script.replace(
                "${NIM_TRITON_HTTP_PORT}",
                "8080"
            )
            compose_services = "kit web"
            compose_up_options = "--no-deps"
            cuda_device_aeronim_env = ""
            default_nim_triton_ip_address = "RETRIEVE_FROM_SSM"
        else:
            # No separate NIM - use the local aeronim compose service.
            user_data_script = user_data_script.replace(
                "${NIM_TRITON_IP_ADDRESS}",
                "aeronim"
            )
            user_data_script = user_data_script.replace(
                "${NIM_TRITON_HTTP_PORT}",
                "8080"
            )
            compose_services = "aeronim kit web"
            compose_up_options = ""
            cuda_device_aeronim_env = "CUDA_DEVICE_AERONIM=0"
            default_nim_triton_ip_address = "aeronim"

        # S3 source substitutions
        from stacks.repo_artifact_stack import RepoArtifactStack
        if repo_bucket is None:
            raise ValueError("repo_bucket is required — source code is always pulled from S3")
        user_data_script = user_data_script.replace("${REPO_S3_BUCKET}", repo_bucket.bucket_name)
        user_data_script = user_data_script.replace("${REPO_S3_PREFIX}", RepoArtifactStack.REPO_PREFIX)
        user_data_script = user_data_script.replace("${COMPOSE_SERVICES}", compose_services)
        user_data_script = user_data_script.replace("${COMPOSE_UP_OPTIONS}", compose_up_options)
        user_data_script = user_data_script.replace("${CUDA_DEVICE_AERONIM_ENV}", cuda_device_aeronim_env)
        user_data_script = user_data_script.replace("${DEFAULT_NIM_TRITON_IP_ADDRESS}", default_nim_triton_ip_address)

        # Add the script to user data
        user_data.add_commands(user_data_script)

        # Use Deep Learning AMI with NVIDIA drivers pre-installed
        # This AMI includes CUDA and NVIDIA drivers
        machine_image = ec2.MachineImage.lookup(
            name="Deep Learning OSS Nvidia Driver AMI GPU PyTorch 2.* (Ubuntu 22.04) *",
            owners=["amazon"],
        )

        # Select instance type based on deployment mode
        if use_external_nim:
            # Split deployment: Only Kit + Web, 1 GPU sufficient
            instance_type_str = "g5.2xlarge"  # 1x A10G, 8 vCPU, 32GB RAM - $1.006/hr
            volume_size = 300
            deployment_mode = "split"
        else:
            # Single instance: Kit + NIM + Web, needs more CPU/RAM for both workloads
            # 24GB VRAM is tight when shared, but sufficient with good memory management
            instance_type_str = "g5.4xlarge"  # 1x A10G, 8 vCPU, 32GB RAM - $1.212/hr
            volume_size = 350
            deployment_mode = "single"

        print(f"  Compute instance: {instance_type_str} ({deployment_mode} mode)")

        # EC2 Instance
        # Instance type selection rationale:
        #   Split mode (g5.2xlarge):
        #     - Kit only needs ~8-12GB VRAM
        #     - 4 vCPU adequate for single workload
        #     - Cost: $1.006/hr
        #
        #   Single mode (g5.2xlarge):
        #     - Kit + NIM share 24GB VRAM (tight but functional)
        #     - 8 vCPU better for concurrent workloads
        #     - More RAM helps with buffer management
        #     - Cost: $1.212/hr

        # Select subnet in an AZ with capacity
        instance = ec2.Instance(
            self,
            "OmniverseInstance",
            instance_type=ec2.InstanceType(instance_type_str),
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
                        volume_size=volume_size,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        iops=3000,
                        encrypted=True,
                        delete_on_termination=True,
                    ),
                )
            ],
            user_data_causes_replacement=True,
            require_imdsv2=True,
        )

        ngc_param = ssm.StringParameter.from_string_parameter_name(
            self,
            "NGCParameter",
            string_parameter_name="/omniverse-cae/ngc-secret-name",
        )
        ngc_param.grant_read(instance_role)

        # Add NIM IP as instance tag if using external NIM
        if use_external_nim:
            #from aws_cdk import Tags
            #nim_private_ip = Fn.import_value("OmniverseCAENimStack-PrivateIP")
            #Tags.of(instance).add("NimPrivateIP", nim_private_ip)

            nim_ip_param = ssm.StringParameter.from_string_parameter_name(
                self,
                "NIMIPParameter",
                string_parameter_name="/omniverse-cae/nim-ip"
            )
            nim_ip_param.grant_read(instance_role)

        # No shared security group needed - connections configured above

        # Store security group for connectivity stack
        self.security_group = security_group

        # Outputs
        CfnOutput(
            self,
            "InstanceId",
            value=instance.instance_id,
            description="EC2 Instance ID",
        )

        CfnOutput(
            self,
            "InstancePublicIP",
            value=instance.instance_public_ip,
            description="Public IP address to access the application (changes on restart)",
        )

        CfnOutput(
            self,
            "ApplicationURL",
            value=Fn.sub("http://${IP}", {"IP": instance.instance_public_ip}),
            description="Access the Omniverse CAE Blueprint at this URL",
        )

        CfnOutput(
            self,
            "SSMConnectCommand",
            value=f"aws ssm start-session --target {instance.instance_id}",
            description="Connect to instance via Session Manager",
        )

        CfnOutput(
            self,
            "InstancePrivateIP",
            value=instance.instance_private_ip,
            description="Private IP address of the instance",
        )

        CfnOutput(
            self,
            "SecurityGroupId",
            value=security_group.security_group_id,
            description="Security Group ID - use this to add your IP address",
            export_name=f"{self.stack_name}-SecurityGroupId",
        )


        CfnOutput(
            self,
            "NGCSecretName",
            value=ngc_secret_name,
            description="Secrets Manager secret name containing NGC API key",
        )

        if use_external_nim:
            CfnOutput(
                self,
                "NimEndpoint",
                value=Fn.sub(
                    "http://${NimIP}:8080",
                    {"NimIP": Fn.import_value("OmniverseCAENimStack-PrivateIP")}
                ),
                description="NIM API endpoint (separate instance)",
            )
        else:
            CfnOutput(
                self,
                "NimEndpoint",
                value="http://localhost:8080 (local container)",
                description="NIM API endpoint (co-located)",
            )
