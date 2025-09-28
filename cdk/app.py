#!/usr/bin/env python3
"""CDK application entrypoint for the resume tailoring platform."""
from aws_cdk import App, Environment

from .frontend_stack import FrontendStack
from .backend_stack import BackendStack
from .auth_stack import AuthStack


app = App()

env = Environment(account=app.node.try_get_context("account"), region=app.node.try_get_context("region"))

auth_stack = AuthStack(app, "ResumeAuthStack", env=env)
backend_stack = BackendStack(
    app,
    "ResumeBackendStack",
    user_pool=auth_stack.user_pool,
    identity_pool=auth_stack.identity_pool,
    env=env,
)
FrontendStack(
    app,
    "ResumeFrontendStack",
    api_url=backend_stack.api_url,
    user_pool=auth_stack.user_pool,
    identity_pool=auth_stack.identity_pool,
    env=env,
)

app.synth()
