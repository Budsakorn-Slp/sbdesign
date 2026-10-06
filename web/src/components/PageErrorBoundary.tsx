import { Component, type ReactNode } from "react";
import { isChunkError, reloadForNewVersion } from "../lib/staleChunk";

/** ครอบเนื้อหาของหน้า — หน้าพังต้องไม่กลายเป็นจอขาวทั้งเว็บ
 *
 * โหลดโค้ดหน้าไม่ขึ้นเพราะมีเวอร์ชันใหม่ → รีโหลดให้เอง
 * พังด้วยเหตุอื่น → โชว์กล่องบอกพร้อมปุ่มรีเฟรช หัวเว็บกับเมนูยังใช้ได้
 */
export default class PageErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { err: unknown }> {
  state = { err: null as unknown };

  static getDerivedStateFromError(err: unknown) {
    return { err };
  }

  componentDidCatch(err: unknown) {
    if (isChunkError(err)) reloadForNewVersion();
  }

  componentDidUpdate(prev: { resetKey?: string }) {
    // เปลี่ยนหน้าแล้ว ล้างสถานะพังของหน้าก่อน
    if (prev.resetKey !== this.props.resetKey && this.state.err) this.setState({ err: null });
  }

  render() {
    if (!this.state.err) return this.props.children;
    const chunk = isChunkError(this.state.err);
    return (
      <main className="container sec">
        <div className="note warn" style={{ maxWidth: 560 }}>
          <b>{chunk ? "มีเว็บเวอร์ชันใหม่" : "หน้านี้แสดงผลไม่สำเร็จ"}</b>
          <div className="small" style={{ margin: "6px 0 10px" }}>
            {chunk ? "กำลังโหลดเวอร์ชันใหม่ให้ — ถ้าค้างอยู่ กดปุ่มด้านล่าง" : "ลองโหลดหน้าใหม่อีกครั้ง ถ้ายังเป็นอยู่แจ้งทีม IT"}
          </div>
          <button className="btn dark sm" onClick={() => window.location.reload()}>รีเฟรชหน้า</button>
        </div>
      </main>
    );
  }
}
