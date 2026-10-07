const tones = ["violet", "blue", "rose", "sky", "clay", "indigo"];
export default function Avatar({ name, index = 0, small = false }: { name: string; index?: number; small?: boolean }) {
  return <span aria-hidden="true" className={`avatar avatar-${tones[index % tones.length]} ${small ? "avatar-small" : ""}`}>{Array.from(name.trim())[0]?.toUpperCase() || "?"}</span>;
}
