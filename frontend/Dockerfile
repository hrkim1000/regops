FROM node:22-alpine

ENV NEXT_TELEMETRY_DISABLED=1
WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
# `npm ci`, not `npm install`: it installs exactly the tree in the lockfile and fails if the
# lockfile and package.json disagree. `npm install` is free to resolve something newer, which is
# how an image ends up with a dependency nobody chose — including one an audit has flagged. The
# lockfile is no longer optional in the COPY either: a missing one used to be silently tolerated,
# and the whole point of pinning is that its absence is an error.
RUN npm ci

COPY frontend/ ./

EXPOSE 3000
CMD ["npm", "run", "dev"]
