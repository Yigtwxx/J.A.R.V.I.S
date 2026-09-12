FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# No build-time configuration: the browser only ever calls this app's own origin,
# and app/api/proxy relays to the backend using BACKEND_URL and API_KEY, both read
# at RUNTIME on the server. Nothing about the backend is baked into the bundle.
RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
