import LegacyViewRedirect from "@/components/shell/LegacyViewRedirect";
import ShopView from "@/components/views/ShopView";

/** Home: the shop (what customers use). Under the hood, Docs and GitHub are in the header. */
export default function Home() {
  return (
    <>
      <LegacyViewRedirect />
      <ShopView />
    </>
  );
}
