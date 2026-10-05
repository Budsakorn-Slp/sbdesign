# อิมเมจ API — แยกสองชั้น: prod (ค่าเริ่มต้น) กับ dev
#
#   docker build ./backend                      -> prod  (ไม่มีเครื่องมือเทส ไม่ seed ไม่รันด้วย root)
#   docker build ./backend --target dev         -> dev   (มี pytest ฯลฯ · docker-compose.yml ใช้ตัวนี้)
#
# เดิมมีชั้นเดียวและลง requirements-dev.txt เสมอ แปลว่าของที่ขึ้น prd มี pytest/เครื่องมือ
# เทสติดไปด้วย = พื้นที่โจมตีกว้างกว่าที่จำเป็นโดยไม่ได้อะไรกลับมา

FROM python:3.12-slim AS base
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod +x docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]


# ---- dev: เพิ่มเครื่องมือเทส รันด้วย root เพื่อให้ mount โค้ดจากเครื่องเข้ามาแก้ได้ ----
FROM base AS dev
RUN pip install --no-cache-dir -r requirements-dev.txt


# ---- prod: ชั้นสุดท้าย = ค่าเริ่มต้นของ docker build ----
FROM base AS prod
# ไม่รันด้วย root — ถ้ามีช่องโหว่ในแอป จะได้ไม่ได้สิทธิ์เต็มเครื่องไปด้วย
RUN useradd --create-home --uid 10001 sbapp && chown -R sbapp:sbapp /app
USER sbapp
