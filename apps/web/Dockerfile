FROM node:22-alpine AS base

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable && corepack prepare pnpm@10.11.1 --activate

FROM base AS build

ARG WEB_INTERNAL_API_URL=http://localhost:8000
ENV WEB_INTERNAL_API_URL=$WEB_INTERNAL_API_URL

WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
RUN pnpm build

FROM base AS runtime

ENV NODE_ENV=production
WORKDIR /app
COPY --from=build --chown=node:node /app ./

USER node
EXPOSE 3000
CMD ["pnpm", "start", "--hostname", "0.0.0.0", "--port", "3000"]
