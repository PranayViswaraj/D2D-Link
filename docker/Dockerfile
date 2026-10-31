# Reproducible open-source EDA environment for D2D-Link.
# Uses distro packages (small download) instead of the 600 MB OSS CAD Suite.
FROM ubuntu:24.04
ARG VERIBLE=v0.0-4298-g085eef05
ARG SBY_TAG=yosys-0.33
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential make git curl ca-certificates python3 python3-venv python3-dev \
      time && rm -rf /var/lib/apt/lists/*
# Verilator 5.020, Yosys 0.33, SMT solvers
RUN apt-get update && apt-get install -y --no-install-recommends \
      verilator yosys z3 boolector && rm -rf /var/lib/apt/lists/*
# Optional site CA (e.g. antivirus/proxy TLS inspection root): put it in docker/local-ca.crt.
# The file is git-ignored; without it the build uses the stock CA bundle.
COPY docker/ /tmp/ctx/
RUN if [ -f /tmp/ctx/local-ca.crt ]; then cp /tmp/ctx/local-ca.crt /usr/local/share/ca-certificates/; fi \
      && update-ca-certificates --fresh && rm -rf /tmp/ctx
# SymbiYosys matching the distro Yosys version
RUN mkdir /tmp/sby && curl -fsSL https://github.com/YosysHQ/sby/archive/refs/tags/${SBY_TAG}.tar.gz \
      | tar -xz -C /tmp/sby --strip-components=1 \
      && make -C /tmp/sby install PREFIX=/usr/local && rm -rf /tmp/sby
RUN curl -fsSL https://github.com/chipsalliance/verible/releases/download/${VERIBLE}/verible-${VERIBLE}-linux-static-x86_64.tar.gz \
      | tar -xz -C /opt && ln -s /opt/verible-${VERIBLE} /opt/verible
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
ENV PATH=/opt/venv/bin:/opt/verible/bin:$PATH
WORKDIR /work
