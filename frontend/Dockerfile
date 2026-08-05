FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install

COPY frontend/ ./

EXPOSE 3000
CMD ["npm", "run", "dev"]
