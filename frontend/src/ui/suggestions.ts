import type { QueryMode } from "@domain/models";

/** Exemples cliquables pour tester l'outil sans rien écrire. */
export const SUGGESTIONS: Record<QueryMode, string[]> = {
  ask: [
    "Que propose-t-il sur l’intelligence artificielle\u00a0?",
    "Veut-il baisser les impôts des entreprises\u00a0?",
    "Que propose-t-il sur l’immigration\u00a0?",
    "Est-il favorable à la retraite par capitalisation\u00a0?",
    "Veut-il construire de nouveaux réacteurs nucléaires\u00a0?",
    "Que propose-t-il pour l’école\u00a0?",
  ],
  search: [
    "intelligence artificielle",
    "impôts de production",
    "police municipale",
    "retraite par capitalisation",
    "nucléaire",
    "carte scolaire",
  ],
};
