import { SessionBoundary } from "@/features/auth/SessionBoundary";
// Server component: routing/composition only. Authenticated data stays client-side.
export default function HomePage() {
  return <SessionBoundary />;
}
