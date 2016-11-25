package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._

object Forum {

  val feeder = csv("forums.csv").random

  val init = exec(
    http("Forum init")
      .get(C2corgConf.forum_url + "/")
      .headers(C2corgConf.header_html))

  val open = feed(feeder).exec(
    http("Open forum")
      .get(C2corgConf.forum_url + "/c/${forum_name}/l/latest.json")
      .headers(C2corgConf.header_discourse_1))

  val scroll = feed(feeder).exec(
    http("Scroll forum")
      .get(C2corgConf.forum_url + "/c/${forum_name}/l/latest")
      .headers(C2corgConf.header_discourse_2))

  val post = exec(
    http("Open forum composer")
      .get(C2corgConf.forum_url + "/composer_messages?composer_action=createTopic")
      .headers(Auth.header_discourse_1))
    .pause(13).exec(
      http("Draft")
        .post(C2corgConf.forum_url + "/draft.json")
        .headers(Auth.header_discourse_2)
        .formParam("draft_key", "new_topic")
        .formParam("data", """{"reply":"sdfsfsdf","action":"createTopic","title":"Test again","categoryId":null,"postId":null,"archetypeId":"regular","metaData":null,"composerTime":14914,"typingTime":1900}""")
        .formParam("sequence", "255"))
    .pause(10).exec(
      http("Similar topics")
        .get(C2corgConf.forum_url + "/similar_topics?title=Test%20again&raw=Du%20contenu%20pour%20le%20message")
        .headers(Auth.header_discourse_1))
    .pause(5).exec(
      http("Post message")
        .post(C2corgConf.forum_url + "/posts")
        .headers(Auth.header_discourse_3)
        .formParam("raw", "Du contenu pour le message")
        .formParam("title", "Test again")
        .formParam("unlist_topic", "false")
        .formParam("category", "6")
        .formParam("is_warning", "false")
        .formParam("archetype", "regular")
        .formParam("typing_duration_msecs", "3500")
        .formParam("composer_open_duration_msecs", "40049")
        .formParam("nested_post", "true")
        .check(
          status.is(200),
          jsonPath("$.post.topic_id").exists.saveAs("topic_id")
        ))
    .exec(
      http("List of posts")
        .get(C2corgConf.forum_url + "/t/${topic_id}.json?track_visit=true&forceLoad=true")
        .headers(Auth.header_discourse_4))
}
