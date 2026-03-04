"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

interface NavItem {
  label: string;
  icon: string;
  href: string;
}

const mainNav: NavItem[] = [
  { label: "Dashboard", icon: "pi pi-home", href: "" },
  { label: "Documents", icon: "pi pi-file", href: "/documents" },
  { label: "Search", icon: "pi pi-search", href: "/search" },
  { label: "Compounds", icon: "pi pi-th-large", href: "/compounds" },
  { label: "Chat", icon: "pi pi-comments", href: "/chat" },
];

const bottomNav: NavItem[] = [
  { label: "Settings", icon: "pi pi-cog", href: "/settings" },
];

function NavLink({
  item,
  workspaceSlug,
  pathname,
}: {
  item: NavItem;
  workspaceSlug: string;
  pathname: string;
}) {
  const fullHref = `/${workspaceSlug}${item.href}`;
  const isActive =
    item.href === ""
      ? pathname === `/${workspaceSlug}`
      : pathname.startsWith(fullHref);

  return (
    <Link
      href={fullHref}
      className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
        isActive
          ? "bg-blue-50 text-blue-700 font-medium"
          : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
      }`}
    >
      <i className={`${item.icon} text-base`} />
      <span>{item.label}</span>
    </Link>
  );
}

export function Sidebar({ workspaceSlug }: { workspaceSlug: string }) {
  const pathname = usePathname();

  return (
    <aside className="flex h-full w-56 flex-col border-r border-gray-200 bg-white">
      <nav className="flex flex-1 flex-col gap-1 px-3 py-4">
        {mainNav.map((item) => (
          <NavLink
            key={item.label}
            item={item}
            workspaceSlug={workspaceSlug}
            pathname={pathname}
          />
        ))}
      </nav>
      <nav className="border-t border-gray-200 px-3 py-4">
        {bottomNav.map((item) => (
          <NavLink
            key={item.label}
            item={item}
            workspaceSlug={workspaceSlug}
            pathname={pathname}
          />
        ))}
      </nav>
    </aside>
  );
}
