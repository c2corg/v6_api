# shellcheck shell=bash
# Shell prompt: user ➜ cwd (branch <|>|<>|=) $
# Installed in /etc/bash.bashrc by the Dockerfile.

[ -n "$PS1" ] || return 0
. /usr/lib/git-core/git-sh-prompt

# shellcheck disable=SC2034  # read by git-sh-prompt
GIT_PS1_SHOWUPSTREAM="auto"     # < behind, > ahead, <> diverged, = in sync
unset GIT_PS1_SHOWDIRTYSTATE GIT_PS1_SHOWSTASHSTATE GIT_PS1_SHOWUNTRACKEDFILES

__c2c_prompt() {
    __git_ps1 \
        '\[\e[0;32m\]\u \[\e[0m\]➜ \[\e[1;34m\]\w\[\e[0m\]' \
        ' \$ ' \
        ' \[\e[0;36m\](\[\e[1;31m\]%s\[\e[0;36m\])\[\e[0m\]'
}
PROMPT_COMMAND="__c2c_prompt${PROMPT_COMMAND:+; $PROMPT_COMMAND}"
