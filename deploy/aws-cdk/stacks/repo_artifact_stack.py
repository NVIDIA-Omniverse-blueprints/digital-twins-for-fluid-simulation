import os
from aws_cdk import (
    Stack,
    RemovalPolicy,
    Size,
    aws_s3 as s3,
    aws_s3_deployment as s3_deployment,
)
from constructs import Construct


class RepoArtifactStack(Stack):
    """
    Uploads the local repository to a dedicated S3 bucket so that EC2 instances
    can pull source code from S3 instead of cloning from GitHub.

    The bucket and prefix are exported as stack attributes so ComputeStack can
    grant the instance role read access and inject the coordinates into user data.
    Make sure Git LFS files and submodules are present before deploying; data and
    stage assets are intentionally included in this upload.
    """

    # S3 key prefix under which all repo files are stored.
    REPO_PREFIX = "repo"

    def __init__(self, scope: "Construct", construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.bucket = s3.Bucket(
            self,
            "RepoArtifactBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=False,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
        )

        # Repo root is three directories above this file:
        #   stacks/ → aws-cdk/ → deploy/ → digital-twins-for-fluid-simulation/
        repo_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )

        s3_deployment.BucketDeployment(
            self,
            "RepoUpload",
            sources=[
                s3_deployment.Source.asset(
                    repo_root,
                    exclude=[
                        ".git",
                        ".git/**",
                        ".env",
                        "**/.env",
                        "**/.env.*",
                        "*.etl",
                        "*.etli",
                        "*.swp",
                        "*.swo",
                        "*~",
                        # Build artifact directories — enumerate explicitly.
                        # A bare `_*` would also match `__init__.py`, stripping
                        # every Python package marker from the upload and
                        # breaking the kit-cae prebuild link step.
                        "**/_build",
                        "**/_build/**",
                        "**/_repo",
                        "**/_repo/**",
                        "**/_compiler",
                        "**/_compiler/**",
                        "logs",
                        "logs/**",
                        "**/logs",
                        "**/logs/**",
                        "**/*.log",
                        ".venv",
                        ".venv/**",
                        "venv",
                        "venv/**",
                        "env",
                        "env/**",
                        "ENV",
                        "ENV/**",
                        "*.egg-info",
                        "**/*.egg-info",
                        "**/*.egg-info/**",
                        "deploy/aws-cdk/cdk.out",
                        "deploy/aws-cdk/cdk.out/**",
                        "deploy/aws-cdk/.venv",
                        "deploy/aws-cdk/.venv/**",
                        "**/__pycache__",
                        "**/__pycache__/**",
                        "**/*.pyc",
                        "**/.pytest_cache",
                        "**/.pytest_cache/**",
                        "**/.mypy_cache",
                        "**/.mypy_cache/**",
                        "**/.hypothesis",
                        "**/.hypothesis/**",
                        "**/.tox",
                        "**/.tox/**",
                        "**/node_modules",
                        "**/node_modules/**",
                        "web-app/app",
                        "web-app/app/**",
                        "**/.DS_Store",
                    ],
                )
            ],
            destination_bucket=self.bucket,
            destination_key_prefix=self.REPO_PREFIX,
            # Increase Lambda limits for large repos with LFS content.
            memory_limit=1024,
            ephemeral_storage_size=Size.gibibytes(5),
            retain_on_delete=False,
        )
