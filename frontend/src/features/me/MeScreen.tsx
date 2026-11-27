import { useApp } from "../../app/context";
import { Icon, ScreenHead } from "../../components/ui";

const LINKS = [
  { href: "#/journey", icon: "journey", title: "My Journey", body: "Your permanent record: achievements, learning, decisions, by year." },
  { href: "#/insights", icon: "insights", title: "Insights", body: "Where your time went, what moved forward, what keeps slipping." },
  { href: "#/reminders", icon: "bell", title: "Reminders and calendar", body: "Phone notifications, reminders, and your plan in Google Calendar." },
  { href: "#/partners", icon: "people", title: "Accountability", body: "Optional. Share chosen goals and progress with someone you trust." },
  { href: "#/profile", icon: "profile", title: "Settings", body: "Timezone, categories, reminder preferences, health log, history." },
  { href: "#/account", icon: "edit", title: "Account and privacy", body: "Password, privacy notice, sign out." },
  { href: "#/feedback", icon: "sparkle", title: "Beta feedback", body: "Report a bug or suggest an improvement." },
];

export function MeScreen() {
  const app = useApp();
  return (
    <section className="screen" aria-labelledby="me-title">
      <ScreenHead eyebrow="Me" title={app.user.display_name || "You"} lead="Your history, your patterns and the people you choose to share them with." />
      <ul className="menu-cards">
        {[...LINKS, ...(app.user.is_beta_admin ? [{ href: "#/beta", icon: "flag", title: "Beta admin", body: "Invite friends, reset links, read feedback." }] : [])].map((link) => (
          <li key={link.href}>
            <a href={link.href}>
              <span className="menu-icon" aria-hidden="true">
                <Icon name={link.icon} />
              </span>
              <span>
                <b>{link.title}</b>
                <small>{link.body}</small>
              </span>
              <Icon name="chevronRight" />
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
