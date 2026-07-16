import { actions, levers } from "./actions";
import { clients } from "./clients";
import { health } from "./health";
import { insights, notifications } from "./insights";
import { metrics } from "./metrics";
import { rankings } from "./rankings";
import { recommendations } from "./recommendations";
import { experiments } from "./experiments";
import { auth, cloudflare, google, onboarding, settings } from "./settings";
import { summaries, tasks } from "./tasks";

export const api = {
  clients,
  metrics,
  insights,
  tasks,
  summaries,
  actions,
  settings,
  levers,
  notifications,
  onboarding,
  cloudflare,
  google,
  auth,
  rankings,
  health,
  recommendations,
  experiments,
};
