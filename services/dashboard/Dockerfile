# Dashboard image (Service C). Build context is ./services/dashboard (see docker-compose.yml).
FROM node:20-slim

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
# Vite dev server, bound to all interfaces so it's reachable from the host.
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
