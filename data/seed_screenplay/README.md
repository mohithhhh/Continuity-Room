# Seed screenplay: "The Last Ledger"

A synthetic, public-domain 3-episode drama written for this project's demo
dataset. No copyrighted material is used. Three continuity errors are
deliberately planted so the pipeline has something real to find:

1. **Character injury contradiction** — Mara's hand is bandaged (right hand,
   burned) at the end of Episode 1, Scene 3, but she is shown playing piano
   with both hands, undamaged, in Episode 2, Scene 1, with no time skip or
   healing explanation. (`episode_1.md` Scene 3 vs `episode_2.md` Scene 1)

2. **Prop contradiction** — Dev's grandfather's watch is established as
   destroyed/thrown into the river in Episode 1, Scene 5, but he is wearing
   it again in Episode 3, Scene 2, described in identical detail. (`episode_1.md`
   Scene 5 vs `episode_3.md` Scene 2)

3. **Location/timeline contradiction** — Episode 2, Scene 4 establishes it is
   raining heavily and has been for days in the coastal town, but Episode 2,
   Scene 5 (immediately following, same night per the script) describes a
   dry, dusty road with no rain — inconsistent weather/location continuity
   within the same episode. (`episode_2.md` Scene 4 vs Scene 5)

Ingest all three files through the pipeline (technical producer → director →
studio head) to populate `story_events` and see these three surface as
`continuity_flags`.
