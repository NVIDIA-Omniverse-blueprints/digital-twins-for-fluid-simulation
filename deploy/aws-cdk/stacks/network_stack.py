from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
)
from constructs import Construct


class NetworkStack(Stack):
    """
    Network stack creating VPC with public and private subnets.
    Simplified design for single EC2 instance deployment.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC with public and private subnets across 2 AZs
        # Note: Explicitly select AZs to avoid capacity issues
        # For eu-west-1: use eu-west-1b and eu-west-1c (avoid eu-west-1a for g5 instances)
        self.vpc = ec2.Vpc(
            self,
            "OmniverseVPC",
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            max_azs=2,
            availability_zones=None,  # Let AWS choose, will be filtered by compute stack
            nat_gateways=1,  # Single NAT gateway for cost optimization
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
            ],
            enable_dns_hostnames=True,
            enable_dns_support=True,
        )

        # Outputs
        CfnOutput(
            self,
            "VPCId",
            value=self.vpc.vpc_id,
            description="VPC ID",
            export_name=f"{self.stack_name}-VPCId",
        )

        CfnOutput(
            self,
            "VPCCidr",
            value=self.vpc.vpc_cidr_block,
            description="VPC CIDR Block",
        )
