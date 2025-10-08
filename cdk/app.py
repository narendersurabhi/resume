#!/usr/bin/env python3
from aws_cdk import App, Environment

from .frontend_stack import FrontendStack
from .backend_stack import BackendStack
from .auth_stack import AuthStack

app = App()

env = Environment(
    account=app.node.try_get_context("account"),
    region=app.node.try_get_context("region"),
)

auth_stack = AuthStack(app, "ResumeAuthStack", env=env)
backend_stack = BackendStack(app, "ResumeBackendStack", env=env)
frontend_stack = FrontendStack(app, "ResumeFrontendStack", env=env)

# Frontend relies on exports from Auth + Backend
frontend_stack.add_dependency(auth_stack)
frontend_stack.add_dependency(backend_stack)

app.synth()
