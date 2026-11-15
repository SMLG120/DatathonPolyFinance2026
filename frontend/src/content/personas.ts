import type { PersonaId } from "@/lib/contracts";

/**
 * Persona facts shown on the picker before any portfolio is loaded.
 *
 * Age, occupation, objective, horizon and risk profile are the facts given in
 * the official case (pages 5–7). The case gives the personas no portfolio and
 * no numbers: those are invented for this simulation and come from the service
 * (or from the fixtures), never from this file.
 */
export interface PersonaCard {
  persona_id: PersonaId;
  name: string;
  age: number;
  occupation: string;
  objective: string;
  horizon: string;
  risk_profile: string;
  /** What this persona demonstrates in the product. */
  demonstrates: string;
  role_label: string;
  /** False while the persona is outside the core scope. */
  available: boolean;
}

export const PERSONAS: PersonaCard[] = [
  {
    persona_id: "robert",
    name: "Robert",
    age: 59,
    occupation: "Healthcare professional",
    objective: "Preserve capital while keeping some growth potential.",
    horizon: "3 to 5 years",
    risk_profile: "Low to moderate",
    demonstrates: "A purchase that is tempting but may not fit the rules he confirmed.",
    role_label: "Primary demonstration",
    available: true,
  },
  {
    persona_id: "mateo",
    name: "Mateo",
    age: 41,
    occupation: "Operations manager",
    objective: "Balanced capital growth over the medium and long term.",
    horizon: "8 to 12 years",
    risk_profile: "Moderate",
    demonstrates: "A preference that must be defined before it can be checked, and data that is missing.",
    role_label: "Second demonstration",
    available: true,
  },
  {
    persona_id: "amira",
    name: "Amira",
    age: 26,
    occupation: "Software engineer",
    objective: "Grow capital over the long term.",
    horizon: "15 years or more",
    risk_profile: "High",
    demonstrates: "Wording that needs clarification rather than a verdict.",
    role_label: "Third demonstration",
    available: true,
  },
];

export const DEFAULT_PERSONA: PersonaId = "robert";

export function personaName(personaId: PersonaId | null): string {
  return PERSONAS.find((p) => p.persona_id === personaId)?.name ?? "No persona";
}
