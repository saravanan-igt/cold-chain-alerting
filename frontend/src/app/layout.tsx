import type { Metadata } from "next";
import type { ReactNode } from "react";
import "bootstrap/dist/css/bootstrap.min.css";
import "@/styles/globals.scss";
export const metadata: Metadata = {
  title: "Coldline · Fleet operations",
  description:
    "Evidence-led cold-chain operations with customer-specific rules.",
};
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
