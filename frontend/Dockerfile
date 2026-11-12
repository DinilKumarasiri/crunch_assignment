# Node 22 LTS on a small Alpine Linux base
FROM node:22-alpine

WORKDIR /app

# Same caching trick as the backend: install dependencies first,
# so code changes don't trigger a slow reinstall.
COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev"]