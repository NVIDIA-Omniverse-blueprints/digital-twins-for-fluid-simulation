#!/usr/bin/env python3
"""CDK entry point for the Omniverse CAE Blueprint AWS deployment."""
import os
import re
import aws_cdk as cdk
from aws_cdk import Fn
from stacks.config_stack import ConfigStack
from stacks.network_stack import NetworkStack
from stacks.compute_stack import ComputeStack
from stacks.nim_compute_stack import NimComputeStack
from stacks.connectivity_stack import ConnectivityStack
from stacks.repo_artifact_stack import RepoArtifactStack

tags = {
    "project": "caebluep",
    "description": "CAE Blueprint on AWS Run"
}

app = cdk.App()


def context_bool(name: str, default: bool) -> bool:
    value = app.node.try_get_context(name)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "y", "on"):
            return True
        if normalized in ("0", "false", "no", "n", "off"):
            return False
    raise ValueError(f"{name} must be a boolean value")


env = cdk.Environment(
    account=os.getenv("AWS_ACCOUNT_ID"),
    region=os.getenv("AWS_REGION")
)

split_deployment = context_bool("splitDeployment", True)
allowed_ip_ranges = app.node.try_get_context("allowedIpRanges") or None

MATCH_RANGES_PATTERN = r"[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}/[3][0-9]"
assert allowed_ip_ranges is None or re.match(MATCH_RANGES_PATTERN, allowed_ip_ranges), \
    "allowedIpRanges must be a valid IP range in Format X.X.X.X/X"

config_stack = ConfigStack(
    app,
    "OmniverseCAEConfigStack",
    tags=tags,
    env=env,
    description="Shared configuration: NGC API key in Secrets Manager",
)

# Uploads the local repo to S3; all EC2 instances pull source from here.
repo_artifact_stack = RepoArtifactStack(
    app,
    "OmniverseCAERepoArtifactStack",
    tags=tags,
    env=env,
    description="S3 bucket holding local repo snapshot; EC2 instances pull source from here",
)

network_stack = NetworkStack(
    app,
    "OmniverseCAENetworkStack",
    tags=tags,
    env=env,
    description="Network infrastructure for Omniverse CAE Blueprint"
)

if split_deployment:
    print("=" * 80)
    print("SPLIT DEPLOYMENT MODE")
    print("Deploying NIM and Omniverse/Frontend on separate instances")
    print("=" * 80 + "\n")

    nim_stack = NimComputeStack(
        app,
        "OmniverseCAENimStack",
        vpc=network_stack.vpc,
        repo_bucket=repo_artifact_stack.bucket,
        tags=tags,
        env=env,
        description="NIM compute infrastructure for Omniverse CAE Blueprint"
    )
    nim_stack.add_dependency(network_stack)
    nim_stack.add_dependency(config_stack)
    nim_stack.add_dependency(repo_artifact_stack)

    compute_stack = ComputeStack(
        app,
        "OmniverseCAEComputeStack",
        vpc=network_stack.vpc,
        use_external_nim=True,
        repo_bucket=repo_artifact_stack.bucket,
        tags=tags,
        env=env,
        description="Omniverse/Frontend compute infrastructure for CAE Blueprint"
    )
    compute_stack.add_dependency(network_stack)
    compute_stack.add_dependency(config_stack)
    compute_stack.add_dependency(nim_stack)
    compute_stack.add_dependency(repo_artifact_stack)

    connectivity_stack = ConnectivityStack(
        app,
        "OmniverseCAEConnectivityStack",
        omniverse_sg_id=Fn.import_value("OmniverseCAEComputeStack-SecurityGroupId"),
        nim_sg_id=Fn.import_value("OmniverseCAENimStack-SecurityGroupId"),
        tags=tags,
        env=env,
        allowed_ip_ranges=allowed_ip_ranges,
        description="Security group connectivity for User-2-Kit-2-NIM"
    )
    connectivity_stack.add_dependency(compute_stack)
    connectivity_stack.add_dependency(nim_stack)

else:
    print("\n" + "=" * 80)
    print("SINGLE INSTANCE DEPLOYMENT MODE")
    print("Deploying all components on one instance")
    print("=" * 80 + "\n")

    compute_stack = ComputeStack(
        app,
        "OmniverseCAEComputeStack",
        vpc=network_stack.vpc,
        use_external_nim=False,
        repo_bucket=repo_artifact_stack.bucket,
        tags=tags,
        env=env,
        description="Compute infrastructure for Omniverse CAE Blueprint"
    )
    compute_stack.add_dependency(network_stack)
    compute_stack.add_dependency(config_stack)
    compute_stack.add_dependency(repo_artifact_stack)

    connectivity_stack = ConnectivityStack(
        app,
        "OmniverseCAEConnectivityStack",
        omniverse_sg_id=Fn.import_value("OmniverseCAEComputeStack-SecurityGroupId"),
        # NIM is co-located — allow intra-SG access
        nim_sg_id=Fn.import_value("OmniverseCAEComputeStack-SecurityGroupId"),
        tags=tags,
        env=env,
        allowed_ip_ranges=allowed_ip_ranges,
        description="Security group connectivity for User-2-Kit-and-NIM"
    )
    connectivity_stack.add_dependency(compute_stack)

app.synth()
