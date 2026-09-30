/** โครงการ์ดเปล่าระหว่างรอข้อมูล — รูปทรงต้องเท่าการ์ดจริง ไม่งั้นของกระโดดตอนข้อมูลมาถึง */
export default function ProductCardSkeleton() {
  return (
    <article className="pcard skel" aria-hidden="true">
      <div className="skel-box" style={{ aspectRatio: "1 / 1" }} />
      <div className="pcard-body">
        <div className="skel-line" style={{ width: "90%" }} />
        <div className="skel-line" style={{ width: "55%" }} />
        <div className="skel-line" style={{ width: "40%", marginTop: 6 }} />
        <div className="skel-line lg" style={{ width: "50%", marginTop: 8 }} />
      </div>
    </article>
  );
}

/** ใส่ในกริดเดียวกับการ์ดจริงได้เลย — ใช้ตอนโหลดหน้าแรกและตอนเลื่อนลงโหลดหน้าถัดไป */
export function ProductCardSkeletonGrid({ count }: { count: number }) {
  return (
    <>
      {Array.from({ length: count }, (_, i) => (
        <ProductCardSkeleton key={i} />
      ))}
    </>
  );
}
