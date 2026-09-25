"use client";

import {
  BarChart3,
  BookOpen,
  Briefcase,
  Columns3,
  Globe,
  House,
  Mail,
  MessageCircle,
  Search,
  SlidersHorizontal,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { AutopilotSwitch, useAutopilotText } from "@/components/autopilot-switch";
import { useTasks } from "@/components/providers/tasks";
import { useUI } from "@/components/providers/ui-state";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuBadge,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";

type Item = { href: string; label: string; icon: LucideIcon; count?: "reminders" | "chats_pending" };

const MAIN: Item[] = [
  { href: "/", label: "Сегодня", icon: House },
  { href: "/hh", label: "HeadHunter", icon: Briefcase },
  { href: "/pipeline", label: "Воронка", icon: Columns3, count: "reminders" },
  { href: "/chats", label: "Чаты", icon: MessageCircle, count: "chats_pending" },
  { href: "/mail", label: "Письма компаниям", icon: Mail },
  { href: "/sites", label: "Другие сайты", icon: Globe },
];

const TOOLS: Item[] = [
  { href: "/answers", label: "База ответов", icon: BookOpen },
  { href: "/stats", label: "Статистика", icon: BarChart3 },
  { href: "/settings", label: "Настройки", icon: SlidersHorizontal },
];

export function Logo() {
  return (
    <div className="grid size-[34px] place-items-center rounded-[10px] border-[1.5px] border-foreground bg-brand">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="3.5" y="7" width="17" height="13" rx="4.5" stroke="#141414" strokeWidth="2" />
        <circle cx="9.5" cy="13.5" r="1.5" fill="#141414" />
        <circle cx="14.5" cy="13.5" r="1.5" fill="#141414" />
        <path d="M12 7V4" stroke="#141414" strokeWidth="2" strokeLinecap="round" />
      </svg>
    </div>
  );
}

function NavGroup({ label, items }: { label: string; items: Item[] }) {
  const pathname = usePathname();
  const { status } = useTasks();
  const { setOpenMobile } = useSidebar();
  return (
    <SidebarGroup>
      <SidebarGroupLabel>{label}</SidebarGroupLabel>
      <SidebarGroupContent>
        <SidebarMenu>
          {items.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const count = item.count ? (status?.[item.count] ?? 0) : 0;
            return (
              <SidebarMenuItem key={item.href}>
                <SidebarMenuButton
                  asChild
                  isActive={active}
                  className="h-9 rounded-xl text-[14.5px] font-medium data-[active=true]:bg-primary data-[active=true]:font-semibold data-[active=true]:text-primary-foreground data-[active=true]:[&>svg]:text-brand"
                >
                  <Link href={item.href} onClick={() => setOpenMobile(false)}>
                    <item.icon />
                    <span>{item.label}</span>
                  </Link>
                </SidebarMenuButton>
                {count > 0 && (
                  <SidebarMenuBadge className="rounded-full bg-brand px-1.5 font-bold text-brand-foreground">{count}</SidebarMenuBadge>
                )}
              </SidebarMenuItem>
            );
          })}
        </SidebarMenu>
      </SidebarGroupContent>
    </SidebarGroup>
  );
}

export function AppSidebar() {
  const { setSearchOpen } = useUI();
  const autopilotText = useAutopilotText();
  return (
    <Sidebar>
      <SidebarHeader className="gap-5 px-3.5 pt-5">
        <div className="flex items-center gap-2.5 px-2">
          <Logo />
          <b className="text-lg font-extrabold tracking-[-0.02em]">kolenke</b>
        </div>
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          className="flex w-full items-center gap-2.5 rounded-xl border bg-surface-2 px-3 py-2 text-left text-sm text-muted-foreground hover:border-ink-2 hover:text-ink-2"
        >
          <Search className="size-4" />
          Поиск
          <kbd className="ml-auto rounded border px-1.5 font-mono text-[11px] opacity-70">⌘K</kbd>
        </button>
      </SidebarHeader>
      <SidebarContent className="px-1.5">
        <NavGroup label="Главное" items={MAIN} />
        <NavGroup label="Инструменты" items={TOOLS} />
      </SidebarContent>
      <SidebarFooter className="p-3.5">
        <div className="rounded-2xl border bg-surface-2 p-3.5">
          <div className="flex items-center justify-between font-semibold">
            <label htmlFor="sidebar-autopilot">Автопилот</label>
            <AutopilotSwitch id="sidebar-autopilot" />
          </div>
          <p className="mt-1.5 text-[13px] text-muted-foreground">{autopilotText}</p>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
