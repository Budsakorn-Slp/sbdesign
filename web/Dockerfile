# อิมเมจหน้าเว็บ — แยกสองชั้นเหมือนฝั่ง API
#
#   docker build ./web                  -> prod  (build เป็นไฟล์นิ่ง แล้วเสิร์ฟด้วย nginx)
#   docker build ./web --target dev     -> dev   (vite dev server · docker-compose.yml ใช้ตัวนี้)
#
# เดิมมีชั้นเดียวและ CMD คือ "npm run dev" ซึ่งถ้าเอาขึ้นเซิร์ฟเวอร์จริงแปลว่า:
#   - แจก source map = คนนอกอ่านซอร์สหน้าบ้านได้ทั้งหมดเหมือนเปิดโปรเจ็คดู
#   - เปิดช่อง HMR (websocket ของ vite) ที่ไม่ได้ออกแบบมาให้โผล่สู่อินเทอร์เน็ต
#   - ช้ากว่ามาก เพราะ transpile สดทุก request แทนที่จะเสิร์ฟไฟล์ที่ build แล้ว

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install


# ---- dev: vite dev server ----
FROM deps AS dev
COPY . .
EXPOSE 5173
CMD ["npm", "run", "dev"]


# ---- build: tsc + vite build -> /app/dist ----
FROM deps AS build
COPY . .
RUN npm run build


# ---- prod: nginx เสิร์ฟไฟล์นิ่ง + ส่งต่อ /api กับ /ws ไปที่ api ----
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY nginx-security.conf /etc/nginx/snippets/sb-security.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
