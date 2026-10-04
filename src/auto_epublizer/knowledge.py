"""统一术语库/知识库编排：持久化目录解析 + git 持续维护 + 命令实现。

- 目录解析优先级：``--dir`` > 环境变量 ``AUTO_EPUBLIZER_HOME`` > 配置
  ``paths.knowledge_dir`` > 默认 ``~/Documents/auto-epublizer``。
- 远端解析优先级：``--remote`` > 环境变量 ``AUTO_EPUBLIZER_REMOTE`` > 配置
  ``paths.knowledge_remote`` > 公共仓库 ``DEFAULT_KNOWLEDGE_REMOTE``（已固化在
  ``auto_common.config``，``knowledge init`` 无需手填即可配好远端）。
- git：``init`` / ``commit`` / ``push``（本地确定性操作；失败仅告警，不阻断术语合并）；
  提交时若环境未配置 git 身份则注入兜底身份，保证无身份机器上也能确定性提交。
- 内容：术语表 CSV 的读写/合并/导出复用 ``auto_translator.glossary.store``（纯函数）；
- 裁决：跨书冲突外置到 ``conflicts.jsonl`` 待 agent 裁决（单 LLM 原则，CLI 不裁决）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from auto_common.config import DEFAULT_KNOWLEDGE_REMOTE, Config
from auto_common.workspace import RunStore
from auto_translator.glossary import (
    GlossaryEntry,
    export_for_workspace,
    load_glossary_csv,
    load_legacy_category_csv,
    load_store_csv,
    merge_workspace_glossary,
    read_store_conflicts,
    save_store_csv,
    store_stats,
    write_store_conflicts,
    write_workspace_terms,
)

DEFAULT_STORE_DIRNAME = "auto-epublizer"

_STORE_README = """# auto-epublizer 统一术语库 / 知识库

本目录由 `auto-epublizer` 的 **agent** 自行维护，跨工作区（跨书）复用，避免重复考据与
重复裁决。作为**公共** git 仓库持续维护，推送到 GitHub 跨设备同步，其他人亦可只读订阅复用。

- 远端：<https://github.com/Misaka0x26FE/auto-epublizer-knowledge>
- 该地址已固化在 `auto-epublizer` 软件里（`auto_common.config.DEFAULT_KNOWLEDGE_REMOTE`），
  `knowledge init` 无需手填 `--remote` 即可配好远端。

## 许可证

本库内容（`terminology.csv`、`conflicts.jsonl`、`knowledge/*.md`）采用
**[CC BY-SA 4.0](LICENSE)** 授权：他人可自由使用、改编与再发布，须署名且以相同许可证共享。

> 注意：本许可证仅覆盖本库**内容**。`auto-epublizer` **软件本体**采用 AGPL-3.0
> （见其仓库 `LICENSE`），两者互不覆盖。

## 目录结构

- `terminology.csv` —— 统一术语表（列 = 工作区 `glossary.csv` + 溯源列
  `src_lang,tgt_lang,book`）；键为 `(src_lang, tgt_lang, source)`。
- `conflicts.jsonl` —— 跨书术语冲突账本（append-only，待 agent 裁决）。
- `knowledge/` —— 知识库（agent 自由撰写的 markdown：人物考据、体例决策、经验）。

## 只读订阅（他人复用）

```bash
git clone https://github.com/Misaka0x26FE/auto-epublizer-knowledge.git
```

本库不含任何书稿正文，仅有词条映射与 agent 撰写的判据/体例笔记。

## 用法（维护者）

```bash
auto-epublizer knowledge path                      # 查看本目录与覆盖来源
auto-epublizer knowledge export --workspace <ws>   # 同语对已确认术语 → preprocessing/terms.csv
auto-epublizer knowledge import --workspace <ws>   # 工作区 glossary.csv → 统一库（合并 + 自动提交）
auto-epublizer knowledge status                    # 统计 + git 状态
auto-epublizer knowledge push                      # 推送到远端（跨设备同步）
```

**裁决**：`conflicts.jsonl` 与 `terminology.csv` 中同一键出现多个译法时，由 agent 阅读
证据后直接编辑 `terminology.csv`（保留一个、删除/清空其余），未裁决计数随之归零。
"""

_KNOWLEDGE_INDEX = """# 知识库目录（INDEX）

本目录由 agent 自行维护：人物/地名考据、机构与专名决议、体例与风格决策、踩坑经验。
每篇一主题，文件名用 `YYYY-MM-DD-<主题>.md`，正文建议含「判据 / 处置 / 验证」三段。
在下方登记条目，便于后续工作区快速检索。

| 文件 | 主题 | 关联书目/语对 |
|---|---|---|
| （示例）2026-09-25-napoleon-name.md | 拿破仑译名统一 | en->zh-CN |
"""

_STORE_LICENSE = """Attribution-ShareAlike 4.0 International

=======================================================================

Creative Commons Corporation ("Creative Commons") is not a law firm and
does not provide legal services or legal advice. Distribution of
Creative Commons public licenses does not create a lawyer-client or
other relationship. Creative Commons makes its licenses and related
information available on an "as-is" basis. Creative Commons gives no
warranties regarding its licenses, any material licensed under their
terms and conditions, or any related information. Creative Commons
disclaims all liability for damages resulting from their use to the
fullest extent possible.

Using Creative Commons Public Licenses

Creative Commons public licenses provide a standard set of terms and
conditions that creators and other rights holders may use to share
original works of authorship and other material subject to copyright
and certain other rights specified in the public license below. The
following considerations are for informational purposes only, are not
exhaustive, and do not form part of our licenses.

     Considerations for licensors: Our public licenses are
     intended for use by those authorized to give the public
     permission to use material in ways otherwise restricted by
     copyright and certain other rights. Our licenses are
     irrevocable. Licensors should read and understand the terms
     and conditions of the license they choose before applying it.
     Licensors should also secure all rights necessary before
     applying our licenses so that the public can reuse the
     material as expected. Licensors should clearly mark any
     material not subject to the license. This includes other CC-
     licensed material, or material used under an exception or
     limitation to copyright. More considerations for licensors:
    wiki.creativecommons.org/Considerations_for_licensors

     Considerations for the public: By using one of our public
     licenses, a licensor grants the public permission to use the
     licensed material under specified terms and conditions. If
     the licensor's permission is not necessary for any reason--for
     example, because of any applicable exception or limitation to
     copyright--then that use is not regulated by the license. Our
     licenses grant only permissions under copyright and certain
     other rights that a licensor has authority to grant. Use of
     the licensed material may still be restricted for other
     reasons, including because others have copyright or other
     rights in the material. A licensor may make special requests,
     such as asking that all changes be marked or described.
     Although not required by our licenses, you are encouraged to
     respect those requests where reasonable. More considerations
     for the public:
    wiki.creativecommons.org/Considerations_for_licensees

=======================================================================

Creative Commons Attribution-ShareAlike 4.0 International Public
License

By exercising the Licensed Rights (defined below), You accept and agree
to be bound by the terms and conditions of this Creative Commons
Attribution-ShareAlike 4.0 International Public License ("Public
License"). To the extent this Public License may be interpreted as a
contract, You are granted the Licensed Rights in consideration of Your
acceptance of these terms and conditions, and the Licensor grants You
such rights in consideration of benefits the Licensor receives from
making the Licensed Material available under these terms and
conditions.


Section 1 -- Definitions.

  a. Adapted Material means material subject to Copyright and Similar
     Rights that is derived from or based upon the Licensed Material
     and in which the Licensed Material is translated, altered,
     arranged, transformed, or otherwise modified in a manner requiring
     permission under the Copyright and Similar Rights held by the
     Licensor. For purposes of this Public License, where the Licensed
     Material is a musical work, performance, or sound recording,
     Adapted Material is always produced where the Licensed Material is
     synched in timed relation with a moving image.

  b. Adapter's License means the license You apply to Your Copyright
     and Similar Rights in Your contributions to Adapted Material in
     accordance with the terms and conditions of this Public License.

  c. BY-SA Compatible License means a license listed at
     creativecommons.org/compatiblelicenses, approved by Creative
     Commons as essentially the equivalent of this Public License.

  d. Copyright and Similar Rights means copyright and/or similar rights
     closely related to copyright including, without limitation,
     performance, broadcast, sound recording, and Sui Generis Database
     Rights, without regard to how the rights are labeled or
     categorized. For purposes of this Public License, the rights
     specified in Section 2(b)(1)-(2) are not Copyright and Similar
     Rights.

  e. Effective Technological Measures means those measures that, in the
     absence of proper authority, may not be circumvented under laws
     fulfilling obligations under Article 11 of the WIPO Copyright
     Treaty adopted on December 20, 1996, and/or similar international
     agreements.

  f. Exceptions and Limitations means fair use, fair dealing, and/or
     any other exception or limitation to Copyright and Similar Rights
     that applies to Your use of the Licensed Material.

  g. License Elements means the license attributes listed in the name
     of a Creative Commons Public License. The License Elements of this
     Public License are Attribution and ShareAlike.

  h. Licensed Material means the artistic or literary work, database,
     or other material to which the Licensor applied this Public
     License.

  i. Licensed Rights means the rights granted to You subject to the
     terms and conditions of this Public License, which are limited to
     all Copyright and Similar Rights that apply to Your use of the
     Licensed Material and that the Licensor has authority to license.

  j. Licensor means the individual(s) or entity(ies) granting rights
     under this Public License.

  k. Share means to provide material to the public by any means or
     process that requires permission under the Licensed Rights, such
     as reproduction, public display, public performance, distribution,
     dissemination, communication, or importation, and to make material
     available to the public including in ways that members of the
     public may access the material from a place and at a time
     individually chosen by them.

  l. Sui Generis Database Rights means rights other than copyright
     resulting from Directive 96/9/EC of the European Parliament and of
     the Council of 11 March 1996 on the legal protection of databases,
     as amended and/or succeeded, as well as other essentially
     equivalent rights anywhere in the world.

  m. You means the individual or entity exercising the Licensed Rights
     under this Public License. Your has a corresponding meaning.


Section 2 -- Scope.

  a. License grant.

       1. Subject to the terms and conditions of this Public License,
          the Licensor hereby grants You a worldwide, royalty-free,
          non-sublicensable, non-exclusive, irrevocable license to
          exercise the Licensed Rights in the Licensed Material to:

            a. reproduce and Share the Licensed Material, in whole or
               in part; and

            b. produce, reproduce, and Share Adapted Material.

       2. Exceptions and Limitations. For the avoidance of doubt, where
          Exceptions and Limitations apply to Your use, this Public
          License does not apply, and You do not need to comply with
          its terms and conditions.

       3. Term. The term of this Public License is specified in Section
          6(a).

       4. Media and formats; technical modifications allowed. The
          Licensor authorizes You to exercise the Licensed Rights in
          all media and formats whether now known or hereafter created,
          and to make technical modifications necessary to do so. The
          Licensor waives and/or agrees not to assert any right or
          authority to forbid You from making technical modifications
          necessary to exercise the Licensed Rights, including
          technical modifications necessary to circumvent Effective
          Technological Measures. For purposes of this Public License,
          simply making modifications authorized by this Section 2(a)
          (4) never produces Adapted Material.

       5. Downstream recipients.

            a. Offer from the Licensor -- Licensed Material. Every
               recipient of the Licensed Material automatically
               receives an offer from the Licensor to exercise the
               Licensed Rights under the terms and conditions of this
               Public License.

            b. Additional offer from the Licensor -- Adapted Material.
               Every recipient of Adapted Material from You
               automatically receives an offer from the Licensor to
               exercise the Licensed Rights in the Adapted Material
               under the conditions of the Adapter's License You apply.

            c. No downstream restrictions. You may not offer or impose
               any additional or different terms or conditions on, or
               apply any Effective Technological Measures to, the
               Licensed Material if doing so restricts exercise of the
               Licensed Rights by any recipient of the Licensed
               Material.

       6. No endorsement. Nothing in this Public License constitutes or
          may be construed as permission to assert or imply that You
          are, or that Your use of the Licensed Material is, connected
          with, or sponsored, endorsed, or granted official status by,
          the Licensor or others designated to receive attribution as
          provided in Section 3(a)(1)(A)(i).

  b. Other rights.

       1. Moral rights, such as the right of integrity, are not
          licensed under this Public License, nor are publicity,
          privacy, and/or other similar personality rights; however, to
          the extent possible, the Licensor waives and/or agrees not to
          assert any such rights held by the Licensor to the limited
          extent necessary to allow You to exercise the Licensed
          Rights, but not otherwise.

       2. Patent and trademark rights are not licensed under this
          Public License.

       3. To the extent possible, the Licensor waives any right to
          collect royalties from You for the exercise of the Licensed
          Rights, whether directly or through a collecting society
          under any voluntary or waivable statutory or compulsory
          licensing scheme. In all other cases the Licensor expressly
          reserves any right to collect such royalties.


Section 3 -- License Conditions.

Your exercise of the Licensed Rights is expressly made subject to the
following conditions.

  a. Attribution.

       1. If You Share the Licensed Material (including in modified
          form), You must:

            a. retain the following if it is supplied by the Licensor
               with the Licensed Material:

                 i. identification of the creator(s) of the Licensed
                    Material and any others designated to receive
                    attribution, in any reasonable manner requested by
                    the Licensor (including by pseudonym if
                    designated);

                ii. a copyright notice;

               iii. a notice that refers to this Public License;

                iv. a notice that refers to the disclaimer of
                    warranties;

                 v. a URI or hyperlink to the Licensed Material to the
                    extent reasonably practicable;

            b. indicate if You modified the Licensed Material and
               retain an indication of any previous modifications; and

            c. indicate the Licensed Material is licensed under this
               Public License, and include the text of, or the URI or
               hyperlink to, this Public License.

       2. You may satisfy the conditions in Section 3(a)(1) in any
          reasonable manner based on the medium, means, and context in
          which You Share the Licensed Material. For example, it may be
          reasonable to satisfy the conditions by providing a URI or
          hyperlink to a resource that includes the required
          information.

       3. If requested by the Licensor, You must remove any of the
          information required by Section 3(a)(1)(A) to the extent
          reasonably practicable.

  b. ShareAlike.

     In addition to the conditions in Section 3(a), if You Share
     Adapted Material You produce, the following conditions also apply.

       1. The Adapter's License You apply must be a Creative Commons
          license with the same License Elements, this version or
          later, or a BY-SA Compatible License.

       2. You must include the text of, or the URI or hyperlink to, the
          Adapter's License You apply. You may satisfy this condition
          in any reasonable manner based on the medium, means, and
          context in which You Share Adapted Material.

       3. You may not offer or impose any additional or different terms
          or conditions on, or apply any Effective Technological
          Measures to, Adapted Material that restrict exercise of the
          rights granted under the Adapter's License You apply.


Section 4 -- Sui Generis Database Rights.

Where the Licensed Rights include Sui Generis Database Rights that
apply to Your use of the Licensed Material:

  a. for the avoidance of doubt, Section 2(a)(1) grants You the right
     to extract, reuse, reproduce, and Share all or a substantial
     portion of the contents of the database;

  b. if You include all or a substantial portion of the database
     contents in a database in which You have Sui Generis Database
     Rights, then the database in which You have Sui Generis Database
     Rights (but not its individual contents) is Adapted Material,
     including for purposes of Section 3(b); and

  c. You must comply with the conditions in Section 3(a) if You Share
     all or a substantial portion of the contents of the database.

For the avoidance of doubt, this Section 4 supplements and does not
replace Your obligations under this Public License where the Licensed
Rights include other Copyright and Similar Rights.


Section 5 -- Disclaimer of Warranties and Limitation of Liability.

  a. UNLESS OTHERWISE SEPARATELY UNDERTAKEN BY THE LICENSOR, TO THE
     EXTENT POSSIBLE, THE LICENSOR OFFERS THE LICENSED MATERIAL AS-IS
     AND AS-AVAILABLE, AND MAKES NO REPRESENTATIONS OR WARRANTIES OF
     ANY KIND CONCERNING THE LICENSED MATERIAL, WHETHER EXPRESS,
     IMPLIED, STATUTORY, OR OTHER. THIS INCLUDES, WITHOUT LIMITATION,
     WARRANTIES OF TITLE, MERCHANTABILITY, FITNESS FOR A PARTICULAR
     PURPOSE, NON-INFRINGEMENT, ABSENCE OF LATENT OR OTHER DEFECTS,
     ACCURACY, OR THE PRESENCE OR ABSENCE OF ERRORS, WHETHER OR NOT
     KNOWN OR DISCOVERABLE. WHERE DISCLAIMERS OF WARRANTIES ARE NOT
     ALLOWED IN FULL OR IN PART, THIS DISCLAIMER MAY NOT APPLY TO YOU.

  b. TO THE EXTENT POSSIBLE, IN NO EVENT WILL THE LICENSOR BE LIABLE
     TO YOU ON ANY LEGAL THEORY (INCLUDING, WITHOUT LIMITATION,
     NEGLIGENCE) OR OTHERWISE FOR ANY DIRECT, SPECIAL, INDIRECT,
     INCIDENTAL, CONSEQUENTIAL, PUNITIVE, EXEMPLARY, OR OTHER LOSSES,
     COSTS, EXPENSES, OR DAMAGES ARISING OUT OF THIS PUBLIC LICENSE OR
     USE OF THE LICENSED MATERIAL, EVEN IF THE LICENSOR HAS BEEN
     ADVISED OF THE POSSIBILITY OF SUCH LOSSES, COSTS, EXPENSES, OR
     DAMAGES. WHERE A LIMITATION OF LIABILITY IS NOT ALLOWED IN FULL OR
     IN PART, THIS LIMITATION MAY NOT APPLY TO YOU.

  c. The disclaimer of warranties and limitation of liability provided
     above shall be interpreted in a manner that, to the extent
     possible, most closely approximates an absolute disclaimer and
     waiver of all liability.


Section 6 -- Term and Termination.

  a. This Public License applies for the term of the Copyright and
     Similar Rights licensed here. However, if You fail to comply with
     this Public License, then Your rights under this Public License
     terminate automatically.

  b. Where Your right to use the Licensed Material has terminated under
     Section 6(a), it reinstates:

       1. automatically as of the date the violation is cured, provided
          it is cured within 30 days of Your discovery of the
          violation; or

       2. upon express reinstatement by the Licensor.

     For the avoidance of doubt, this Section 6(b) does not affect any
     right the Licensor may have to seek remedies for Your violations
     of this Public License.

  c. For the avoidance of doubt, the Licensor may also offer the
     Licensed Material under separate terms or conditions or stop
     distributing the Licensed Material at any time; however, doing so
     will not terminate this Public License.

  d. Sections 1, 5, 6, 7, and 8 survive termination of this Public
     License.


Section 7 -- Other Terms and Conditions.

  a. The Licensor shall not be bound by any additional or different
     terms or conditions communicated by You unless expressly agreed.

  b. Any arrangements, understandings, or agreements regarding the
     Licensed Material not stated herein are separate from and
     independent of the terms and conditions of this Public License.


Section 8 -- Interpretation.

  a. For the avoidance of doubt, this Public License does not, and
     shall not be interpreted to, reduce, limit, restrict, or impose
     conditions on any use of the Licensed Material that could lawfully
     be made without permission under this Public License.

  b. To the extent possible, if any provision of this Public License is
     deemed unenforceable, it shall be automatically reformed to the
     minimum extent necessary to make it enforceable. If the provision
     cannot be reformed, it shall be severed from this Public License
     without affecting the enforceability of the remaining terms and
     conditions.

  c. No term or condition of this Public License will be waived and no
     failure to comply consented to unless expressly agreed to by the
     Licensor.

  d. Nothing in this Public License constitutes or may be interpreted
     as a limitation upon, or waiver of, any privileges and immunities
     that apply to the Licensor or You, including from the legal
     processes of any jurisdiction or authority.


=======================================================================

Creative Commons is not a party to its public
licenses. Notwithstanding, Creative Commons may elect to apply one of
its public licenses to material it publishes and in those instances
will be considered the “Licensor.” The text of the Creative Commons
public licenses is dedicated to the public domain under the CC0 Public
Domain Dedication. Except for the limited purpose of indicating that
material is shared under a Creative Commons public license or as
otherwise permitted by the Creative Commons policies published at
creativecommons.org/policies, Creative Commons does not authorize the
use of the trademark "Creative Commons" or any other trademark or logo
of Creative Commons without its prior written consent including,
without limitation, in connection with any unauthorized modifications
to any of its public licenses or any other arrangements,
understandings, or agreements concerning use of licensed material. For
the avoidance of doubt, this paragraph does not form part of the
public licenses.

Creative Commons may be contacted at creativecommons.org.
"""

_STORE_GITIGNORE = """# 运行时/临时/系统文件
*.tmp
.DS_Store
__pycache__/
*.py[cod]
"""


def _default_store_dir() -> Path:
    return Path.home() / "Documents" / DEFAULT_STORE_DIRNAME


def resolve_store_dir(config: Config | None = None, *, override: str | None = None) -> Path:
    """解析统一库目录：override > 环境变量 > 配置 > 默认。"""
    if override:
        return Path(override).expanduser()
    env = os.environ.get("AUTO_EPUBLIZER_HOME")
    if env:
        return Path(env).expanduser()
    if config is not None and config.paths.knowledge_dir:
        return Path(config.paths.knowledge_dir).expanduser()
    return _default_store_dir()


def resolve_remote(config: Config | None = None, *, override: str | None = None) -> str:
    """解析统一库 git 远端：override > 环境变量 > 配置 > 公共仓库默认值。"""
    if override:
        return override
    env = os.environ.get("AUTO_EPUBLIZER_REMOTE")
    if env:
        return env
    if config is not None and config.paths.knowledge_remote:
        return config.paths.knowledge_remote
    return DEFAULT_KNOWLEDGE_REMOTE


def _git_env() -> dict[str, str]:
    """注入兜底 git 身份（仅当环境未提供时），保证无身份机器上也能提交。"""
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "auto-epublizer")
    env.setdefault("GIT_AUTHOR_EMAIL", "auto-epublizer@localhost")
    env.setdefault("GIT_COMMITTER_NAME", "auto-epublizer")
    env.setdefault("GIT_COMMITTER_EMAIL", "auto-epublizer@localhost")
    return env


def git_available() -> bool:
    return shutil.which("git") is not None


def _git(store_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(store_dir), *args],
        capture_output=True,
        text=True,
        env=_git_env(),
        check=False,
    )


def is_git_repo(store_dir: Path) -> bool:
    if not (store_dir / ".git").exists():
        return False
    return _git(store_dir, "rev-parse", "--is-inside-work-tree").returncode == 0


def git_state(store_dir: Path) -> dict:
    """store 的 git 状态快照（只读，不发网络请求）。"""
    if not is_git_repo(store_dir):
        return {"repo": False, "dirty": False, "remote": None, "branch": "", "last_commit": ""}
    dirty = bool(_git(store_dir, "status", "--porcelain").stdout.strip())
    remote = _git(store_dir, "remote", "get-url", "origin")
    branch = _git(store_dir, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    last = _git(store_dir, "log", "-1", "--format=%h %s").stdout.strip()
    return {
        "repo": True,
        "dirty": dirty,
        "remote": remote.stdout.strip() if remote.returncode == 0 else None,
        "branch": branch,
        "last_commit": last,
    }


def git_commit(store_dir: Path, message: str) -> tuple[bool, str]:
    """提交 store 全部改动；无改动/非仓库/失败返回 (False, 原因)。"""
    if not is_git_repo(store_dir):
        return False, "非 git 仓库（先运行 knowledge init）"
    _git(store_dir, "add", "-A")
    result = _git(store_dir, "commit", "-q", "-m", message)
    if result.returncode == 0:
        return True, "已提交"
    combined = (result.stdout + result.stderr).strip()
    if "nothing to commit" in combined:
        return False, "无改动"
    return False, combined or "git commit 失败"


def git_push(store_dir: Path, remote: str = "origin") -> tuple[bool, str]:
    """推送当前分支到远端（需要网络与凭据；失败返回原因，不抛异常）。"""
    if not is_git_repo(store_dir):
        return False, "非 git 仓库（先运行 knowledge init）"
    has_remote = _git(store_dir, "remote", "get-url", remote)
    if has_remote.returncode != 0:
        return False, f"未配置远端 {remote}（用 --remote 或 knowledge init --remote 指定）"
    result = _git(store_dir, "push", "-u", remote, "HEAD")
    if result.returncode == 0:
        return True, "已推送"
    return False, (result.stdout + result.stderr).strip() or "git push 失败"


def _ensure_skeleton(store_dir: Path) -> None:
    (store_dir / "knowledge").mkdir(parents=True, exist_ok=True)
    files = {
        store_dir / "README.md": _STORE_README,
        store_dir / ".gitignore": _STORE_GITIGNORE,
        store_dir / "knowledge" / "INDEX.md": _KNOWLEDGE_INDEX,
        # 公共知识库内容许可证（CC BY-SA 4.0 全文，canonical 文本，见 README 许可证节）
        store_dir / "LICENSE": _STORE_LICENSE,
    }
    for path, content in files.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")
    csv_path = store_dir / "terminology.csv"
    if not csv_path.exists():
        save_store_csv(csv_path, [])
    conflicts = store_dir / "conflicts.jsonl"
    if not conflicts.exists():
        conflicts.write_text("", encoding="utf-8")


def knowledge_init(store_dir: Path, *, remote: str = "", push: bool = False) -> dict:
    """创建 store 骨架 + git init + 首次提交；可选配置远端并首推。"""
    store_dir.mkdir(parents=True, exist_ok=True)
    _ensure_skeleton(store_dir)

    initialized = False
    message = "git 不可用，跳过版本维护"
    if git_available():
        if not is_git_repo(store_dir):
            _git(store_dir, "init", "-q", "-b", "main")
        initialized = True
        if remote:
            existing = _git(store_dir, "remote", "get-url", "origin")
            if existing.returncode == 0:
                _git(store_dir, "remote", "set-url", "origin", remote)
            else:
                _git(store_dir, "remote", "add", "origin", remote)
        committed, message = git_commit(store_dir, "chore(knowledge): 初始化统一术语库/知识库")
        pushed = None
        if push and remote:
            ok, push_msg = git_push(store_dir)
            pushed = {"ok": ok, "message": push_msg}
    else:
        committed, pushed = False, None

    return {
        "store": str(store_dir),
        "initialized": initialized,
        "committed": committed,
        "message": message,
        "remote": remote,
        "pushed": pushed,
    }


def _lang_pair(store: RunStore, src_lang: str | None, tgt_lang: str | None) -> tuple[str, str]:
    pub = store.load_publication()
    src = (src_lang or pub.meta.language or "").strip()
    tgt = (tgt_lang or pub.meta.target_language or "").strip()
    if not src:
        raise ValueError(
            "源语言未知（publication.json.meta.language 为 auto 未回写）："
            "请用 --src-lang 显式声明源语言（ISO 639-1，如 en/ru/ja）"
        )
    return src, tgt


def knowledge_import(
    store_dir: Path,
    store: RunStore,
    *,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    commit: bool = True,
) -> dict:
    """把工作区 glossary.csv 合并进统一库（幂等）+ 冲突外置 + 自动提交。"""
    _ensure_skeleton(store_dir)
    src, tgt = _lang_pair(store, src_lang, tgt_lang)
    pub = store.load_publication()
    glossary_path = store.analysis_dir / "glossary.csv"
    ws_entries = load_glossary_csv(glossary_path)
    store_entries = load_store_csv(store_dir / "terminology.csv")

    result = merge_workspace_glossary(
        store_entries, ws_entries, src_lang=src, tgt_lang=tgt, book=pub.slug
    )
    save_store_csv(store_dir / "terminology.csv", result.entries)
    conflicts_written = write_store_conflicts(store_dir / "conflicts.jsonl", result.conflicts)

    committed, commit_msg = (False, "跳过提交")
    if commit:
        committed, commit_msg = git_commit(
            store_dir,
            f"chore(knowledge): 合并《{pub.slug}》术语（+{result.added} ~{result.updated} "
            f"冲突{conflicts_written}）",
        )

    return {
        "store": str(store_dir),
        "src_lang": src,
        "tgt_lang": tgt,
        "book": pub.slug,
        "merged": len(ws_entries),
        "added": result.added,
        "updated": result.updated,
        "conflicts": conflicts_written,
        "committed": committed,
        "commit_message": commit_msg,
    }


def _load_any_glossary(path: Path) -> list[GlossaryEntry]:
    """读取任意术语 CSV：表头含 category 且无 type 视为旧案例格式。"""
    first_line = path.read_text(encoding="utf-8").splitlines()[:1]
    header = first_line[0].lower() if first_line else ""
    if "category" in header and "type" not in header:
        return load_legacy_category_csv(path)
    return load_glossary_csv(path)


def knowledge_import_file(
    store_dir: Path,
    csv_path: str | Path,
    *,
    src_lang: str,
    tgt_lang: str,
    book: str,
    status: str | None = None,
    commit: bool = True,
) -> dict:
    """把任意术语 CSV 导入统一库（历史项目不是工作区时的确定性入口）。

    - 自动识别旧案例格式（``category,source,target,note``）与标准格式；
    - ``status`` 可强制覆盖条目态（如历史建议统一为 ``seed``）；
    - 幂等合并 + 冲突外置 + 自动 git 提交。
    """
    _ensure_skeleton(store_dir)
    p = Path(csv_path)
    if not p.is_file():
        raise ValueError(f"术语 CSV 不存在：{p}")
    entries = _load_any_glossary(p)
    if status:
        for entry in entries:
            entry.status = status
    store_entries = load_store_csv(store_dir / "terminology.csv")
    result = merge_workspace_glossary(
        store_entries, entries, src_lang=src_lang, tgt_lang=tgt_lang, book=book
    )
    save_store_csv(store_dir / "terminology.csv", result.entries)
    conflicts_written = write_store_conflicts(store_dir / "conflicts.jsonl", result.conflicts)

    committed, commit_msg = (False, "跳过提交")
    if commit:
        committed, commit_msg = git_commit(
            store_dir,
            f"chore(knowledge): 导入《{book}》术语 {len(entries)} 条"
            f"（+{result.added} ~{result.updated} 冲突{conflicts_written}）",
        )
    return {
        "store": str(store_dir),
        "book": book,
        "src_lang": src_lang,
        "tgt_lang": tgt_lang,
        "merged": len(entries),
        "added": result.added,
        "updated": result.updated,
        "conflicts": conflicts_written,
        "committed": committed,
        "commit_message": commit_msg,
    }


def knowledge_export(
    store_dir: Path,
    store: RunStore,
    *,
    src_lang: str | None = None,
    tgt_lang: str | None = None,
    include_pending: bool = False,
    force: bool = False,
) -> dict:
    """把统一库同语对条目导出为工作区 preprocessing/terms.csv（默认仅 confirmed）。"""
    src, tgt = _lang_pair(store, src_lang, tgt_lang)
    store_entries = load_store_csv(store_dir / "terminology.csv")
    entries = export_for_workspace(
        store_entries, src_lang=src, tgt_lang=tgt, include_pending=include_pending
    )
    target = store.preprocessing_dir / "terms.csv"
    if target.exists() and target.read_text(encoding="utf-8").strip() and not force:
        return {
            "store": str(store_dir),
            "src_lang": src,
            "tgt_lang": tgt,
            "target": str(target),
            "count": len(entries),
            "written": False,
            "reason": "preprocessing/terms.csv 已有内容；确认无冲突后加 --force 覆盖",
        }
    write_workspace_terms(target, entries)
    return {
        "store": str(store_dir),
        "src_lang": src,
        "tgt_lang": tgt,
        "target": str(target),
        "count": len(entries),
        "written": True,
        "reason": "",
    }


def knowledge_status(store_dir: Path) -> dict:
    """统一库统计 + git 状态（只读）。"""
    exists = store_dir.is_dir()
    entries = load_store_csv(store_dir / "terminology.csv") if exists else []
    conflicts = read_store_conflicts(store_dir / "conflicts.jsonl") if exists else []
    knowledge_dir = store_dir / "knowledge"
    knowledge_files = (
        sorted(p.name for p in knowledge_dir.glob("*.md")) if knowledge_dir.is_dir() else []
    )
    stats = store_stats(entries)
    stats["conflicts_ledger"] = len(conflicts)
    return {
        "store": str(store_dir),
        "exists": exists,
        "stats": stats,
        "knowledge_files": knowledge_files,
        "git": git_state(store_dir) if exists else {"repo": False},
    }


def knowledge_push(store_dir: Path, *, remote: str = "origin") -> dict:
    """推送 store 到远端（跨设备同步）。"""
    ok, message = git_push(store_dir, remote=remote)
    return {"store": str(store_dir), "remote": remote, "pushed": ok, "message": message}


__all__ = [
    "DEFAULT_KNOWLEDGE_REMOTE",
    "DEFAULT_STORE_DIRNAME",
    "git_available",
    "git_commit",
    "git_push",
    "git_state",
    "is_git_repo",
    "knowledge_export",
    "knowledge_import",
    "knowledge_import_file",
    "knowledge_init",
    "knowledge_push",
    "knowledge_status",
    "resolve_remote",
    "resolve_store_dir",
]
