/** Extensions assessed by `POST /api/security/pe-hints` (`audiotheca.pe_capabilities.PE_EXTS`). */
const PE_EXT = /\.(exe|dll|sys|scr|ocx|cpl|msi)$/i;

export function isPeBinaryFile(name: string): boolean {
  return PE_EXT.test(name);
}
