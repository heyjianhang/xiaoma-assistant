import Image from "next/image";
import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return <Image src="/images/cyber-pony-pixel.webp" width={32} height={32} alt="" aria-hidden="true" className={cn("size-8 shrink-0 object-contain", className)} />;
}
