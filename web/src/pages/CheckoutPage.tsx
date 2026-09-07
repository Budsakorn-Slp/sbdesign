import { Link } from "react-router-dom";
import Icon from "../components/Icon";
import { useCart } from "../lib/cart";
import { bahtWord } from "../lib/format";

export default function CheckoutPage() {
  const { cart } = useCart();
  return (
    <main className="container sec">
      <Link to="/cart" className="row small muted" style={{ marginBottom: 10 }}><Icon name="arrow_back" size={18} /> กลับไปที่ตะกร้า</Link>
      <h1 style={{ fontSize: 26, marginBottom: 12 }}>สั่งซื้อสินค้า</h1>
      <div className="card" style={{ maxWidth: 560 }}>
        <p style={{ margin: 0 }}>ตะกร้า {cart?.no} · {cart?.count || 0} ชิ้น · ยอด {bahtWord(cart?.subtotal || 0)}</p>
        <p className="muted small">หน้าที่อยู่จัดส่ง / ค่าขนส่ง / วิธีชำระเงิน จะเปิดใช้ใน STEP 7–9</p>
      </div>
    </main>
  );
}
