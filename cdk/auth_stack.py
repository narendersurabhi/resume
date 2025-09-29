from aws_cdk import Stack, CfnOutput
from aws_cdk import aws_cognito as cognito
from aws_cdk.aws_cognito_identitypool_alpha import (
    IdentityPool,
    IdentityPoolAuthenticationProviders,
    UserPoolAuthenticationProvider,
)
from constructs import Construct


class AuthStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = cognito.UserPool(
            self,
            "ResumeUserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
        )

        self.user_pool_client = self.user_pool.add_client(
            "ResumeUserPoolClient",
            generate_secret=False,
            prevent_user_existence_errors=True,
        )

        self.identity_pool = IdentityPool(
            self,
            "ResumeIdentityPool",
            identity_pool_name="ResumeIdentityPool",
            authentication_providers=IdentityPoolAuthenticationProviders(
                user_pools=[
                    UserPoolAuthenticationProvider(
                        user_pool=self.user_pool,
                        user_pool_client=self.user_pool_client,
                    )
                ]
            ),
        )

        # 🔹 Export values
        CfnOutput(self, "UserPoolId",
                  value=self.user_pool.user_pool_id,
                  export_name="ResumeUserPoolId")
        CfnOutput(self, "UserPoolClientId",
                  value=self.user_pool_client.user_pool_client_id,
                  export_name="ResumeUserPoolClientId")
        CfnOutput(self, "IdentityPoolId",
                  value=self.identity_pool.identity_pool_id,
                  export_name="ResumeIdentityPoolId")
