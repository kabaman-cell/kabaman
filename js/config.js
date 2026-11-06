/* KABAMAN — Alibaba Open Platform
   When you have an official app key, set alibabaAppKey below.
   Leave it as an empty string until then.
   This site does not call Alibaba while the key is empty.
   A key placed in frontend JavaScript is visible to every visitor,
   so prefer a server later if you connect the real API. */
window.KABAMAN_CONFIG = {
  alibabaAppKey: "",

  /* Supabase Auth for customer accounts.
     Fill these with the Supabase project URL and public anon/publishable key.
     Never put a service_role key or provider secret in this file. */
  supabaseUrl: "",
  supabaseAnonKey: "",
};
