export type AssetKind = "folder" | "audio" | "archive" | "file";
export function LibraryAssetIcon({
  kind,
  large = false,
}: {
  kind: AssetKind;
  large?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={"library-asset-icon kind-" + kind + (large ? " large" : "")}
    >
      {kind === "audio" ? (
        <span className="library-bars">
          <i />
          <i />
          <i />
          <i />
          <i />
        </span>
      ) : (
        <i />
      )}
    </span>
  );
}
