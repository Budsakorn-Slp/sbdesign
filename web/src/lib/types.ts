export type Role = "guest" | "customer" | "sales" | "manager" | "admin";

export type User = {
  id: string;
  role: Exclude<Role, "guest">;
  name: string;
  phone: string | null;
  email: string | null;
  sap_customer_no: string | null;
  staff_code: string | null;
  branch_id: string | null;
  tier: string | null;
  is_guest: boolean;
  default_address: string | null;
  default_postcode: string | null;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
};
