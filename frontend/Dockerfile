FROM node:20-bookworm-slim

ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY=localhost,127.0.0.1

ENV NEXT_TELEMETRY_DISABLED=1
ENV npm_config_registry=${NPM_REGISTRY}
ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV NO_PROXY=${NO_PROXY}

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .

EXPOSE 3000

CMD ["npx", "next", "dev", "--hostname", "0.0.0.0", "--port", "3000"]
