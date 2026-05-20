from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    CfnOutput,
    Fn,
)
from constructs import Construct


class ConnectivityStack(Stack):
    """
    Connectivity stack managing security group rules between Omniverse and NIM instances.
    This stack handles the mutual access configuration to avoid cyclic dependencies.
    Uses imported security group IDs rather than direct references.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        omniverse_sg_id: str,
        nim_sg_id: str,
        allowed_ip_ranges: str = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Import security groups by ID to avoid cyclic references
        omniverse_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "OmniverseSecurityGroup",
            security_group_id=omniverse_sg_id,
        )

        nim_sg = ec2.SecurityGroup.from_security_group_id(
            self,
            "NimSecurityGroup",
            security_group_id=nim_sg_id,
        )

        # Allow Omniverse instance to access NIM API on port 8080
        nim_sg.add_ingress_rule(
            peer=omniverse_sg,
            connection=ec2.Port.tcp(8080),
            description="Allow Omniverse instance to access NIM API",
        )

# Get allowed IP ranges or allow noone
        if allowed_ip_ranges:
            if isinstance(allowed_ip_ranges, str):
                allowed_ip_ranges = [allowed_ip_ranges]

            for ip_range in allowed_ip_ranges:
                print("="*80)
                print(f"Ingress rule to access Frontend for IP range: {ip_range}")
                print("="*80 + "\n")
                # HTTP for web frontend
                peer="User IP Access"
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.tcp(80),
                    description=f"HTTP web access from {peer}",
                )

                # HTTPS for web frontend
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.tcp(443),
                    description=f"HTTPS web access from {peer}",
                )

                # WebRTC/Streaming UDP port
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.udp(1024),
                    description=f"WebRTC UDP from {peer}",
                )

                # Kit streaming TCP ports
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.tcp_range(47995, 48012),
                    description=f"Kit streaming TCP from {peer}",
                )

                # Kit streaming UDP ports
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.udp_range(47995, 48012),
                    description=f"Kit streaming UDP from {peer}",
                )

                # Kit additional TCP ports
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.tcp_range(49000, 49007),
                    description=f"Kit additional TCP from {peer}",
                )

                # Kit additional UDP ports
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.udp_range(49000, 49007),
                    description=f"Kit additional UDP from {peer}",
                )

                # Kit management port
                omniverse_sg.add_ingress_rule(
                    peer=ec2.Peer.ipv4(ip_range),
                    connection=ec2.Port.tcp(49100),
                    description=f"Kit management from {peer}",
                )

        else:
            allowed_ip_ranges = "NOT CONFIGURED: rerun cdk deploy with -c allowedIpRanges=YOUR_IP/32"
            print("\n" + "="*80)
            print("WARNING: No allowed IP ranges specified, so you have no access to the frontend. probably you want to cdk deploy with -c allowedIpRanges=YOUR_IP/32")
            print("="*80 + "\n")


        # Outputs
        CfnOutput(
            self,
            "ConnectivityStatus",
            value="Configured: Omniverse can access NIM on port 8080",
            description="Security group connectivity status",
        )

        CfnOutput(
            self,
            "UserAccessAllowedFrom",
            value=str(allowed_ip_ranges),
            description="Security group connectivity status",
        )
