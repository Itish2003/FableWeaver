import { useMemo } from 'react';

/**
 * Hook to parse chapter outputs and extract evolution data.
 * Each chapter's text contains embedded JSON with stakes_tracking, timeline, etc.
 */
export default function useChapterEvolution(history) {
  const evolution = useMemo(() => {
    if (!history || !Array.isArray(history)) return [];

    return history.map((chapter, index) => {
      const chapterNumber = chapter.sequence || index + 1;
      const result = {
        chapterNumber,
        summary: chapter.summary || null,
        changes: {
          stakes_tracking: null,
          timeline: null,
          divergences_created: [],
          canon_events_addressed: [],
          power_limitations_shown: [],
          character_voices_used: [],
        },
        hasData: false,
      };

      // Try to parse the JSON metadata from chapter text
      try {
        const text = chapter.text || '';

        // Look for JSON block that contains "summary" and structured data
        // The JSON is typically at the end of the chapter text
        const jsonPatterns = [
          /```json\s*(\{[\s\S]*?"summary"[\s\S]*?\})\s*```/,
          /(\{[\s\S]*?"summary"[\s\S]*?"character_voices_used"[\s\S]*?\][\s\S]*?\})/,
          /(\{[\s\S]*?"stakes_tracking"[\s\S]*?\})\s*$/,
        ];

        let parsed = null;
        for (const pattern of jsonPatterns) {
          const match = text.match(pattern);
          if (match) {
            try {
              parsed = JSON.parse(match[1]);
              break;
            } catch {
              continue;
            }
          }
        }

        if (parsed) {
          result.hasData = true;

          // Extract summary if not already set
          if (parsed.summary && !result.summary) {
            result.summary = parsed.summary;
          }

          // Extract stakes tracking
          if (parsed.stakes_tracking) {
            result.changes.stakes_tracking = {
              costs_paid: parsed.stakes_tracking.costs_paid || [],
              near_misses: parsed.stakes_tracking.near_misses || [],
              power_debt_incurred: parsed.stakes_tracking.power_debt_incurred || {},
              consequences_triggered: parsed.stakes_tracking.consequences_triggered || [],
            };
          }

          // Extract timeline data
          if (parsed.timeline) {
            result.changes.timeline = {
              chapter_start_date: parsed.timeline.chapter_start_date,
              chapter_end_date: parsed.timeline.chapter_end_date,
              time_elapsed: parsed.timeline.time_elapsed,
            };
            result.changes.divergences_created = parsed.timeline.divergences_created || [];
            result.changes.canon_events_addressed = parsed.timeline.canon_events_addressed || [];
          }

          // Extract other metadata
          result.changes.power_limitations_shown = parsed.power_limitations_shown || [];
          result.changes.character_voices_used = parsed.character_voices_used || [];
        }
      } catch (e) {
        console.warn(`Failed to parse chapter ${chapterNumber} metadata:`, e);
      }

      return result;
    });
  }, [history]);

  return evolution;
}
