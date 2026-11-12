# Prompts for the questions from other model families (decision 12)

Both were sent as they are, each in a new chat without history, to Gemini and to GPT.
`{30}` is the number of questions. The prompts were not changed after the first run,
so the questions stay comparable. Outputs: `gemini-prompt1.jsonl`, `gemini-prompt2.jsonl`,
`gpt-prompt1.jsonl`, `gpt-prompt2.jsonl`; after removing near-duplicates `deduped.jsonl`;
the blind verifier's verdicts `blind-verdicts-2026-11-12.jsonl`.

## Prompt 1: passenger questions

```
You are helping me build a test set for a chatbot that answers questions about baggage rules of the airline Wizz Air. Do NOT search the web and do NOT try to recall the airline's official rules. I want you to behave like real passengers, not like an expert.

Write {30} different questions that real passengers might ask the chatbot about baggage when flying with Wizz Air. Write in English only. Topics to cover (spread the questions across them):
- cabin baggage and trolley bags
- checked baggage
- size and weight limits
- baggage fees and overweight charges
- fares and bundles, and what baggage each includes
- baggage for children and babies
- special baggage (musical instruments, sports equipment, bikes)
- pets and other animals
- restricted or prohibited items (liquids, power banks, batteries, vapes, electronic devices)
- expensive or fragile items, and declared value
- damaged, delayed or lost baggage, and how and when to report it

Rules:
- Each question must be written by a different passenger persona. Vary them: a family with small kids, a budget student, a musician with an instrument, a cyclist, a business traveller, an elderly person, a pet owner, a non-native English speaker with short or imperfect English.
- Vary the style: some short and informal, some long with personal details, some with typos or missing punctuation, some that contain two questions in one.
- Include some questions with specific numbers or units (kg, cm, inches, pounds).
- Do not copy the style of an official FAQ. Write the way people really type into a chat.
- If two questions are about the same fact, keep only one of them.
- Do not answer the questions.

Output format: JSON Lines, one object per line, nothing else:
{"topic": "...", "persona": "...", "question": "..."}
```

## Prompt 2: difficult questions

```
You are helping me test a chatbot that answers questions about baggage rules of the airline Wizz Air. The chatbot must either give a correct, sourced answer or politely refuse when the information is not available. Do NOT search the web and do NOT try to recall the airline's official rules.

Write {30} difficult test questions, written the way a real passenger would type them, in English only. Use these types:

1. false_premise (6 questions): the question assumes a rule or fact that is probably wrong (for example, a made-up free allowance, a wrong size, or a fee that does not exist).
2. edge_case (6): a situation at the boundary of a rule (a bag slightly over a limit, a passenger travelling with a baby and an instrument, two rules that could apply at the same time).
3. multi_topic (6): one question that needs information from two different baggage topics at once (for example cabin bags, checked bags, fees, bundles, children, special baggage, pets, restricted items, damaged or lost baggage).
4. off_topic (3): questions that sound related to a flight but are not about baggage rules (check-in, refunds, seat selection, delays, compensation, visas), or questions about other airlines.
5. specific_detail (6): a question that sounds like an ordinary baggage-policy question, but asks for a very specific detail that a general policy would probably not state (the exact size of one unusual item, a rule for an unusual item, a deadline for one unusual case).
6. live_or_personal (3): questions that need live information or a specific booking (a specific airport, aircraft or flight, current queue times, my ticket, my booking).

Rules:
- Write like real passengers: varied tone, some short and informal, some with typos.
- If two questions are about the same fact, keep only one of them.
- Do not answer the questions.
- Do not mark which questions are answerable. I will check that myself.

Output format: JSON Lines, one object per line, nothing else:
{"type": "...", "question": "..."}
```
