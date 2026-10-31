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
# SymbiYosys matching the distro Yosys version
RUN git clone --depth 1 -b ${SBY_TAG} https://github.com/YosysHQ/sby /tmp/sby \
      && make -C /tmp/sby install PREFIX=/usr/local && rm -rf /tmp/sby
RUN curl -fsSL https://github.com/chipsalliance/verible/releases/download/${VERIBLE}/verible-${VERIBLE}-linux-static-x86_64.tar.gz \
      | tar -xz -C /opt && ln -s /opt/verible-${VERIBLE} /opt/verible
COPY requirements.txt /tmp/requirements.txt
RUN python3 -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt
ENV PATH=/opt/venv/bin:/opt/verible/bin:$PATH
WORKDIR /work
