import { useEffect, useRef, useState } from "react";
import { getDistricts, getProvinces, getSubdistricts, lookupPostcode, searchGeo } from "../lib/geo";
import type { District, PostcodeHit, Province, Subdistrict } from "../lib/types";
import Icon from "./Icon";

/** ไฮไลต์ส่วนที่ตรงกับคำค้น ให้ตาเห็นว่าทำไมบรรทัดนี้ถึงขึ้นมา */
function mark(text: string, term: string) {
  const i = term ? text.indexOf(term) : -1;
  if (i < 0) return text;
  return (
    <>
      {text.slice(0, i)}
      <b>{text.slice(i, i + term.length)}</b>
      {text.slice(i + term.length)}
    </>
  );
}

export type AddressPatch = {
  postcode?: string;
  sub?: string;
  district?: string;
  province?: string;
  area_id?: number | null;
  is_blocked?: boolean;
};

type Props = {
  postcode: string;
  sub: string;
  district: string;
  province: string;
  onChange: (patch: AddressPatch) => void;
};

/** เลือกที่อยู่แบบไล่ต่อกัน — กรอกรหัสไปรษณีย์แล้วเติมจังหวัด/อำเภอให้เอง
 *
 * ไปได้สองทาง เพราะลูกค้าจำคนละอย่าง:
 *   · กรอกรหัส 5 หลัก -> เติมจังหวัด+อำเภอให้ เหลือเลือกแค่ตำบล
 *     (รหัสเดียวคร่อมหลายอำเภอได้ ถ้าเจอหลายอำเภอจะให้เลือกเอง ไม่เดาให้)
 *   · เลือกจังหวัด -> อำเภอ -> ตำบล แล้วรหัสไปรษณีย์เติมเอง
 */
export default function AddressPicker({ postcode, sub, district, province, onChange }: Props) {
  const [provinces, setProvinces] = useState<Province[]>([]);
  const [districts, setDistricts] = useState<District[]>([]);
  const [subs, setSubs] = useState<Subdistrict[]>([]);
  const [provinceId, setProvinceId] = useState<number | null>(null);
  const [districtId, setDistrictId] = useState<number | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  // รหัสที่ค้นไปแล้ว — กันไม่ให้ effect วนกลับมาค้นซ้ำตอนเราเป็นคนเซ็ต postcode เอง
  const looked = useRef("");
  // คำที่พิมพ์ในช่องรหัส แยกจากค่า postcode จริง เพราะพิมพ์ชื่อตำบลค้นได้ด้วย
  const [term, setTerm] = useState(postcode);
  const [hits, setHits] = useState<PostcodeHit[]>([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  useEffect(() => {
    setTerm(postcode); // ถูกเซ็ตมาจากข้างนอก (ที่อยู่หลัก / จังหวัดที่เลือกบน nav)
  }, [postcode]);

  // พิมพ์ไปหาไป — หน่วงไว้หน่อยกันยิงทุกตัวอักษร
  useEffect(() => {
    const t = term.trim();
    if (t.length < 2) {
      setHits([]);
      return;
    }
    let alive = true;
    const id = window.setTimeout(() => {
      searchGeo(t).then((rows) => {
        if (!alive) return;
        setHits(rows);
        setActive(0);
      });
    }, 200);
    return () => {
      alive = false;
      window.clearTimeout(id);
    };
  }, [term]);

  useEffect(() => {
    getProvinces().then(setProvinces).catch(() => setProvinces([]));
  }, []);

  useEffect(() => {
    if (provinceId === null) return setDistricts([]);
    getDistricts(provinceId).then(setDistricts).catch(() => setDistricts([]));
  }, [provinceId]);

  useEffect(() => {
    if (districtId === null) return setSubs([]);
    getSubdistricts(districtId).then(setSubs).catch(() => setSubs([]));
  }, [districtId]);

  // กรอกรหัสครบ 5 หลักเมื่อไร ค่อยไล่ย้อนกลับให้
  useEffect(() => {
    const pc = postcode.trim();
    if (pc.length !== 5 || pc === looked.current) return;
    looked.current = pc;
    let alive = true;
    lookupPostcode(pc).then((hits) => {
      if (!alive) return;
      if (!hits.length) {
        setHint("ไม่พบรหัสไปรษณีย์นี้ — เลือกจังหวัดเองได้");
        return;
      }
      const oneDistrict = hits.every((h) => h.district_id === hits[0].district_id);
      setProvinceId(hits[0].province_id);
      setDistrictId(oneDistrict ? hits[0].district_id : null);
      setBlocked(hits.every((h) => h.is_blocked));
      setHint(oneDistrict ? null : `รหัสนี้ครอบคลุม ${new Set(hits.map((h) => h.district_id)).size} เขต/อำเภอ — เลือกให้ตรงด้วย`);
      onChange({
        province: hits[0].province_th,
        district: oneDistrict ? hits[0].district_th : "",
        sub: hits.length === 1 ? hits[0].subdistrict_th : "",
        area_id: hits[0].area_id,
        is_blocked: hits.every((h) => h.is_blocked),
      });
    });
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [postcode]);

  const pickProvince = (id: number) => {
    const p = provinces.find((x) => x.province_id === id) || null;
    setProvinceId(p ? id : null);
    setDistrictId(null);
    setBlocked(false);
    setHint(null);
    looked.current = ""; // เลือกเองแล้ว รหัสเดิมใช้ไม่ได้ ต้องยอมค้นใหม่ถ้าพิมพ์ซ้ำ
    onChange({ province: p?.name_th || "", district: "", sub: "", postcode: "", area_id: p?.area_id ?? null, is_blocked: false });
  };

  const pickDistrict = (id: number) => {
    const d = districts.find((x) => x.district_id === id) || null;
    setDistrictId(d ? id : null);
    setHint(null);
    onChange({ district: d?.name_th || "", sub: "" });
  };

  const pickSub = (id: number) => {
    const s = subs.find((x) => x.subdistrict_id === id) || null;
    setBlocked(!!s?.is_blocked);
    looked.current = s?.zipcode || "";
    onChange({ sub: s?.name_th || "", postcode: s?.zipcode || "", area_id: s?.area_id ?? null, is_blocked: !!s?.is_blocked });
  };

  /** เลือกจากรายการที่แนะนำ = ได้ครบทั้งบรรทัดในคลิกเดียว ไม่ต้องไล่เลือกทีละช่อง */
  const pickHit = (h: PostcodeHit) => {
    looked.current = h.zipcode; // เซ็ตเองแล้ว ไม่ต้องให้ effect ไล่ย้อนกลับซ้ำ
    setTerm(h.zipcode);
    setOpen(false);
    setProvinceId(h.province_id);
    setDistrictId(h.district_id);
    setBlocked(h.is_blocked);
    setHint(null);
    onChange({
      postcode: h.zipcode,
      province: h.province_th,
      district: h.district_th,
      sub: h.subdistrict_th,
      area_id: h.area_id,
      is_blocked: h.is_blocked,
    });
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (!open || !hits.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => (i + 1) % hits.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => (i - 1 + hits.length) % hits.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      pickHit(hits[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const subId = subs.find((s) => s.name_th === sub)?.subdistrict_id ?? "";

  return (
    <>
      <label className="field geo-ac">
        <span>รหัสไปรษณีย์ (Postal Code) *</span>
        <input
          value={term}
          onChange={(e) => {
            const v = e.target.value;
            setTerm(v);
            setOpen(true);
            // ดันขึ้นไปข้างบนเฉพาะตอนเป็นตัวเลข — พิมพ์ชื่อตำบลค้นได้ แต่ยังไม่ใช่ค่ารหัสไปรษณีย์
            if (/^\d{0,5}$/.test(v)) onChange({ postcode: v });
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)} // ให้คลิกในลิสต์ทันก่อนปิด
          onKeyDown={onKey}
          placeholder="พิมพ์รหัสไปรษณีย์ หรือชื่อแขวง/ตำบล"
          autoComplete="off"
          role="combobox"
          aria-expanded={open && hits.length > 0}
        />
        {open && hits.length > 0 && (
          <ul className="geo-ac-list" onMouseDown={(e) => e.preventDefault()}>
            {hits.map((h, i) => (
              <li
                key={`${h.subdistrict_id}-${h.zipcode}`}
                className={i === active ? "on" : undefined}
                onMouseEnter={() => setActive(i)}
                onClick={() => pickHit(h)}
              >
                {mark(h.subdistrict_th, term)} <i>»</i> {mark(h.district_th, term)} <i>»</i> {mark(h.province_th, term)}{" "}
                <i>»</i> <em>{mark(h.zipcode, term)}</em>
                {h.is_blocked && <span className="geo-ac-off">ส่งไม่ถึง</span>}
              </li>
            ))}
          </ul>
        )}
      </label>
      <label className="field">
        <span>จังหวัด *</span>
        <select value={provinceId ?? ""} onChange={(e) => pickProvince(Number(e.target.value))}>
          <option value="">{province || "เลือกจังหวัด"}</option>
          {provinces.map((p) => (
            <option key={p.province_id} value={p.province_id}>{p.name_th}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>เขต/อำเภอ *</span>
        <select value={districtId ?? ""} onChange={(e) => pickDistrict(Number(e.target.value))} disabled={!districts.length}>
          <option value="">{districts.length ? district || "เลือกเขต/อำเภอ" : "เลือกจังหวัดก่อน"}</option>
          {districts.map((d) => (
            <option key={d.district_id} value={d.district_id}>{d.name_th}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>แขวง/ตำบล *</span>
        <select value={subId} onChange={(e) => pickSub(Number(e.target.value))} disabled={!subs.length}>
          <option value="">{subs.length ? sub || "เลือกแขวง/ตำบล" : "เลือกเขต/อำเภอก่อน"}</option>
          {subs.map((s) => (
            <option key={s.subdistrict_id} value={s.subdistrict_id}>
              {s.name_th} · {s.zipcode}{s.is_blocked ? " (ส่งไม่ถึง)" : ""}
            </option>
          ))}
        </select>
      </label>
      {hint && <div className="note small span2">{hint}</div>}
      {blocked && (
        <div className="note warn small span2">
          <Icon name="warning" size={16} /> พื้นที่นี้รถของเราส่งไม่ถึง — เลือก "ยกกลับ/รับที่สาขา" หรือติดต่อเจ้าหน้าที่เพื่อจัดส่งด้วยขนส่งภายนอก
        </div>
      )}
    </>
  );
}
