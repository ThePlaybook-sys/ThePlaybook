FROM node:22-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
# Dockerfile builds are isolated from the host/service environment by
# design (Railway's own docs: "Docker isolates the build from the host
# environment") -- a Railway service variable only reaches `next build`
# if explicitly declared as a build ARG here. NEXT_PUBLIC_* values are
# statically inlined into the browser bundle at build time, so without
# this, the deployed client ships `undefined` for both and
# `createBrowserClient` throws synchronously on first use (the M6 real
# "Create Account hangs on Please wait..." defect).
ARG NEXT_PUBLIC_SUPABASE_URL
ARG NEXT_PUBLIC_SUPABASE_ANON_KEY
ENV NEXT_PUBLIC_SUPABASE_URL=$NEXT_PUBLIC_SUPABASE_URL
ENV NEXT_PUBLIC_SUPABASE_ANON_KEY=$NEXT_PUBLIC_SUPABASE_ANON_KEY
RUN npm run build

FROM node:22-slim
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /app/.next ./.next
COPY --from=build /app/node_modules ./node_modules
COPY --from=build /app/package.json ./package.json
COPY --from=build /app/next.config.js ./next.config.js
COPY --from=build /app/public ./public

CMD ["npm", "start"]
