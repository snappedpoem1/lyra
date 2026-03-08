import { Badge, Drawer, Group, Stack, Text, Title } from "@mantine/core";
import { useQuery } from "@tanstack/react-query";
import { getTrackDossier } from "@/services/lyraGateway/queries";
import { useUiStore } from "@/stores/uiStore";

export function TrackDossierDrawer() {
  const trackId = useUiStore((state) => state.dossierTrackId);
  const close = useUiStore((state) => state.closeDossier);
  const { data } = useQuery({
    queryKey: ["dossier", trackId],
    queryFn: () => getTrackDossier(trackId ?? ""),
    enabled: Boolean(trackId),
  });

  return (
    <Drawer
      opened={Boolean(trackId && data)}
      onClose={close}
      position="right"
      size="lg"
      classNames={{
        content: "lyra-drawer-content",
        header: "lyra-drawer-header",
        body: "lyra-drawer-body",
      }}
      title={data ? `${data.track.title}` : "Track dossier"}
    >
      {!data ? null : (
        <Stack gap="lg">
          <div>
            <Text className="pane-meta">{data.track.artist} | {data.fileType}</Text>
            <Text className="oracle-track-reason">{data.provenanceNotes[0] ?? "No provenance notes loaded."}</Text>
          </div>
          <Group gap={6}>
            {data.track.scoreChips.map((chip) => (
              <Badge key={chip.key} color="lyra" variant="light">
                {chip.label} {chip.value != null ? Math.round(chip.value * 100) : "?"}
              </Badge>
            ))}
          </Group>
          {data.fact ? (
            <div className="dossier-fact-drop">
              <span className="insight-kicker">Lyra intel</span>
              <p>{data.fact}</p>
            </div>
          ) : null}
          <div className="dossier-grid">
            <section className="inspector-block">
              <Title order={4}>Structure</Title>
              <Text>BPM {Math.round(data.structure?.bpm ?? 0)}</Text>
              <Text>Key {data.structure?.key ?? "unknown"}</Text>
              {data.structure?.hasDrop ? <Text>Drop at {Math.round(data.structure.dropTimestamp ?? 0)}s</Text> : null}
            </section>
            <section className="inspector-block">
              <Title order={4}>Lineage</Title>
              {data.lineage?.length ? (
                data.lineage.map((edge) => (
                  <Text key={`${edge.source}-${edge.target}`}>{`${edge.source} -> ${edge.target} `}<span className="text-dim">({edge.type})</span></Text>
                ))
              ) : (
                <Text className="text-dim">No live lineage thread loaded.</Text>
              )}
            </section>
            <section className="inspector-block">
              <Title order={4}>Samples</Title>
              {data.samples?.length ? (
                data.samples.map((sample, index) => (
                  <Text key={`${sample.artist}-${sample.title}-${index}`}>{sample.artist} - {sample.title} {sample.year ? `(${sample.year})` : ""}</Text>
                ))
              ) : (
                <Text className="text-dim">No sample provenance detected.</Text>
              )}
            </section>
          </div>
        </Stack>
      )}
    </Drawer>
  );
}
