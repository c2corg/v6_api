-- Fixed accounts for developers, all with the password `c2c` (the one set by the anonymization).
-- They reuse the first kept users, so that they own a profile and a contribution history.
-- To be run after the anonymization.

update users.user u
set username = n.name,
    forum_username = n.name,
    email = n.name || '@example.com',
    moderator = n.moderator,
    blocked = n.blocked,
    email_validated = n.validated
from (values
        (1, 'moderator', true, false, true),
        (2, 'user', false, false, true),
        (3, 'blocked', false, true, true),
        (4, 'unvalidated', false, false, false)
     ) as n(rn, name, moderator, blocked, validated)
join (select p.document_id as id, row_number() over (order by p.document_id) as rn
      from guidebook.user_profiles p join users.user x on x.id = p.document_id) picked
  on picked.rn = n.rn
where u.id = picked.id;

do $$
begin
  if (select count(*) from users.user where username in ('moderator', 'user', 'blocked', 'unvalidated')) <> 4 then
    raise exception 'the fixed test accounts could not be created';
  end if;
end
$$;
