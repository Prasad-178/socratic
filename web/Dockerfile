# Web Dockerfile — Node 20
#
# Builds the Next.js app in production mode.
# Runtime env vars (NEXT_PUBLIC_*, etc.) should be passed via docker run -e
# or a .env file mounted at runtime — do NOT bake secrets into the image.

FROM node:20-slim

WORKDIR /app

COPY package.json package-lock.json ./

# Skip postinstall (it tries to run `cd agent && uv sync` which doesn't apply here)
RUN npm ci --ignore-scripts

COPY . .

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
