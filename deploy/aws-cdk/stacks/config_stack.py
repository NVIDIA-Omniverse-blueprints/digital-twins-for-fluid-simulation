from aws_cdk import (
    Stack,
    aws_secretsmanager as secretsmanager,
    CfnOutput,
    CfnParameter,
    SecretValue,
    aws_ssm as ssm,
    RemovalPolicy,
)
from constructs import Construct

NGC_SECRET_DEFAULT_NAME = "omniverse-cae/ngc-apikey"


class ConfigStack(Stack):
    """
    Deploys shared configuration resources, specifically the NGC API key in
    Secrets Manager. Pass the key at deploy time:

        cdk deploy OmniverseCAEConfigStack \
            --parameters OmniverseCAEConfigStack:NGCApiKey=<key>

    All compute stacks read the secret under the same default name used by
    create-ngc-secret.sh so no other stack configuration changes are needed.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        ngc_api_key = CfnParameter(
            self,
            "NGCApiKey",
            type="String",
            no_echo=True,
            allowed_pattern="nvapi-.+",
            constraint_description="The NGC API key must start with 'nvapi-'.",
            description="NVIDIA NGC API key used to authenticate with nvcr.io",
        )

        secret_name = (
            self.node.try_get_context("ngcSecretName") or NGC_SECRET_DEFAULT_NAME
        )

        secret = secretsmanager.Secret(
            self,
            "NGCAPIKey",
            secret_name=secret_name,
            description="NVIDIA NGC API Key for CAE Blueprint",
            secret_string_value=SecretValue.cfn_parameter(ngc_api_key),
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.ngc_secret_name_parameter = ssm.StringParameter(
            self,
            "NGC_Secret_Name",
            parameter_name="/omniverse-cae/ngc-secret-name",
            string_value=secret_name,
        )

        CfnOutput(
            self,
            "NGCSecretName",
            value=secret.secret_name,
            description="Secrets Manager secret name for NGC API key",
            export_name=f"{self.stack_name}-NGCSecretName",
        )

        CfnOutput(
            self,
            "NGCSecretArn",
            value=secret.secret_arn,
            description="Secrets Manager secret ARN for NGC API key",
            export_name=f"{self.stack_name}-NGCSecretArn",
        )
