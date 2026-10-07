FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

# The image lists Yarn's apt repository, whose signing key apt can no longer verify, so every
# `apt-get update` fails, including the ones run by dev container features. Yarn itself stays installed.
RUN rm -f /etc/apt/sources.list.d/yarn.list
