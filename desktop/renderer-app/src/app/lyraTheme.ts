import { createTheme } from "@mantine/core";

export const lyraTheme = createTheme({
  primaryColor: "lyra",
  fontFamily: 'var(--font-ui)',
  fontFamilyMonospace: 'var(--font-mono)',
  headings: {
    fontFamily: 'var(--font-display)',
  },
  defaultRadius: "md",
  colors: {
    lyra: [
      "#edf8dd",
      "#ddf0bb",
      "#cde89a",
      "#bcdf78",
      "#add85a",
      "#a4d347",
      "#8cd94a",
      "#76b43a",
      "#618f2d",
      "#4a6b20",
    ],
    midnight: [
      "#e7edf7",
      "#cfd7e4",
      "#b3bfd1",
      "#97a6bf",
      "#7c8daa",
      "#6c7d97",
      "#546277",
      "#404c5e",
      "#2a3442",
      "#151b24",
    ],
  },
  components: {
    Button: {
      defaultProps: {
        radius: "md",
        variant: "default",
      },
    },
    TextInput: {
      defaultProps: {
        radius: "md",
      },
    },
    NumberInput: {
      defaultProps: {
        radius: "md",
      },
    },
    Card: {
      defaultProps: {
        radius: "lg",
        shadow: "sm",
      },
    },
    Slider: {
      defaultProps: {
        color: "lyra",
      },
    },
    SegmentedControl: {
      defaultProps: {
        color: "lyra",
        radius: "md",
      },
    },
    Badge: {
      defaultProps: {
        radius: "sm",
        variant: "light",
      },
    },
  },
});
