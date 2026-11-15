"""Runtime agent plumbing: Bedrock Converse wrapper, bounded tool loop, tool
registry with enforced schemas, and prompts.

The model never produces a number or a verdict. Tools are deterministic Python
and the server runs the required calculation whatever the model does.
"""
