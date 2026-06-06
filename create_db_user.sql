-- Run this as the postgres superuser in pgAdmin Query Tool
-- (right-click the server → Query Tool)

-- 1. Create the user
CREATE USER invitioapp WITH PASSWORD 'password';

-- 2. Create the database owned by that user
CREATE DATABASE invitioapp OWNER invitioapp;

-- 3. Grant all privileges on the database
GRANT ALL PRIVILEGES ON DATABASE invitioapp TO invitioapp;
