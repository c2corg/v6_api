package c2corg

import scala.concurrent.duration._

import io.gatling.core.Predef._
import io.gatling.http.Predef._
import io.gatling.jdbc.Predef._

object Topic {

  val feeder = csv("topics.csv").random

  val open = feed(feeder).exec(
    http("Open topic")
      .get("/t/${topic_id}.json")
      .headers(C2corgConf.header_discourse_1)
  )

  val scroll = feed(feeder).exec(
    http("Scroll topic")
      .get("/t/${topic_id}/posts.json")
      .headers(C2corgConf.header_discourse_2)
  )
}

