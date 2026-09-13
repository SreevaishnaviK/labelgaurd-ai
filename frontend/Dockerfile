FROM node:22-alpine

WORKDIR /app

# Install dependencies from the existing lockfile first for layer caching.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# Vite dev server: reads VITE_API_URL from the runtime environment
# (provided by docker-compose.yml) and serves on the port compose maps.
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173", "--strictPort"]
