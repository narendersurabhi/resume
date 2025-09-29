#!/usr/bin/env python3
"""CDK application entrypoint for the resume tailoring platform."""
from aws_cdk import App, Environment

from .frontend_stack import FrontendStack
from .backend_stack import BackendStack
from .auth_stack import AuthStack

app = App()

# Pull account and region from CDK context (set via cdk.json or CLI)
env = Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region"),
)

# # 1. Auth resources
# auth_stack = AuthStack(app, "ResumeAuthStack", env=env)

# # 2. Backend (needs Cognito identity pool)
# backend_stack = BackendStack(
#     app,
#     "ResumeBackendStack",
#     user_pool=auth_stack.user_pool,
#     identity_pool=auth_stack.identity_pool,
#     env=env,
# )

# # 3. Frontend (needs Backend API + Cognito resources)
# FrontendStack(
#     app,
#     "ResumeFrontendStack",
#     api_url=backend_stack.api_url,
#     user_pool=auth_stack.user_pool,
#     user_pool_client=auth_stack.user_pool_client,  # <-- fixed
#     identity_pool=auth_stack.identity_pool,
#     env=env,
# )

# # Explicit dependencies
# frontend_stack.add_dependency(auth_stack)
# frontend_stack.add_dependency(backend_stack)

AuthStack(app, "ResumeAuthStack", env=env)
BackendStack(app, "ResumeBackendStack", env=env)
FrontendStack(app, "ResumeFrontendStack", env=env)

app.synth()
