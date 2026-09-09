# Next.js frontend. Build context = ESM_SCM8/frontend/.
# FASTAPI_INTERNAL_BASE_URL must be set at BUILD time: next.config rewrites are
# baked into .next/routes-manifest.json by `next build`, so the runtime env var
# alone does nothing. Default = localhost for ECS (same task, 2 containers);
# Railway passes its service variable as a build arg to override it.
FROM node:22-slim AS builder
WORKDIR /app
ARG FASTAPI_INTERNAL_BASE_URL=http://127.0.0.1:8002
ENV FASTAPI_INTERNAL_BASE_URL=$FASTAPI_INTERNAL_BASE_URL
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ARG FASTAPI_INTERNAL_BASE_URL=http://127.0.0.1:8002
ENV NODE_ENV=production \
    FASTAPI_INTERNAL_BASE_URL=$FASTAPI_INTERNAL_BASE_URL
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/next.config.mjs ./next.config.mjs
# The V3 excel export route spawns scripts/order-v3-excel-worker.mjs, whose
# import graph reaches lib/ and components/ at runtime — none of which are
# part of the .next build output.
COPY --from=builder /app/scripts ./scripts
COPY --from=builder /app/lib ./lib
COPY --from=builder /app/components ./components
EXPOSE 3000
# Bind 0.0.0.0 (not the package.json `-H ::`) so the ALB reaches the task over IPv4.
CMD ["node_modules/.bin/next", "start", "-H", "0.0.0.0", "-p", "3000"]
