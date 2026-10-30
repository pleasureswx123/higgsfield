"""项目所有者的固定业务权限，不包含平台运维、供应商或财务管理。"""
OWNER_PERMISSIONS = frozenset("""project:read project:edit project:manage project:archive member:read member:manage
asset:read asset:upload asset:create asset:edit asset:reference asset:remove asset:download folder:write
 element:read element:create element:edit element:remove element:configure element:import element:copy
content:review generation:create generation:read generation:cancel output:archive
comment:read comment:create comment:edit:own comment:moderate""".split())
